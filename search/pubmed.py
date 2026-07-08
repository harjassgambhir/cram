"""
search/pubmed.py — PubMed / MEDLINE search via E-utilities.
B.2: Fetches full abstracts via efetch after esummary, giving the synthesis
     LLM actual paper content instead of titles only.
"""

import re
import time
import requests
from cram.config import RESULTS_PER_SOURCE, REQUEST_TIMEOUT, NCBI_API_KEY
from cram.log import log, dim, yellow
from cram.provider.openrouter import with_retry
from cram.search.base import cached_search, RateLimiter

# NCBI E-utilities hard limit: 3 req/s without an API key, 10 req/s with one.
# Shared across all worker threads so parallel branches don't trigger 429s.
_NCBI_LIMITER = RateLimiter(min_interval=0.11 if NCBI_API_KEY else 0.34)


def _fetch_abstracts(pmids: list[str]) -> dict[str, dict]:
    """
    Fetch abstracts + publication types via efetch (XML).
    Returns {pmid: {"abstract": str, "pub_types": list[str]}}.
    Falls back gracefully — returns {} on any error.
    """
    if not pmids:
        return {}
    try:
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract",
        }
        if NCBI_API_KEY:
            params["api_key"] = NCBI_API_KEY

        def _do_efetch():
            _NCBI_LIMITER.wait()
            return requests.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
        r = with_retry(_do_efetch, label="pubmed-efetch")
        r.raise_for_status()
        xml = r.text

        result: dict[str, dict] = {}

        # Extract per-article blocks
        articles = re.findall(
            r'<PubmedArticle>(.*?)</PubmedArticle>', xml, re.DOTALL
        )
        for art in articles:
            # PMID
            pm = re.search(r'<PMID[^>]*>(\d+)</PMID>', art)
            if not pm:
                continue
            pmid = pm.group(1)

            # Abstract text (may have multiple AbstractText labels)
            abstract_parts = re.findall(
                r'<AbstractText[^>]*>(.*?)</AbstractText>', art, re.DOTALL
            )
            abstract = " ".join(
                re.sub(r'<[^>]+>', '', p).strip()
                for p in abstract_parts
            ).strip()

            # Publication types
            pub_types = re.findall(
                r'<PublicationType[^>]*>(.*?)</PublicationType>', art
            )
            pub_types = [pt.strip() for pt in pub_types if pt.strip()]

            result[pmid] = {"abstract": abstract[:1500], "pub_types": pub_types}

        return result
    except Exception as e:
        log(yellow(f"     ⚠  PubMed efetch failed: {e}"))
        return {}


def _evidence_grade_from_pub_types(pub_types: list[str]) -> str:
    """
    B.3: Map PubMed PublicationType to evidence grade emoji.
    Prevents LLM from confabulating grades.

    Grades MUST match the legend printed in every report header / config.EVIDENCE_GRADES:
      🟢🟢 Cochrane/meta · 🟢 RCT · 🟡🟡 SR/cohort · 🟡 cohort · 🟠 case-control ·
      🔴 case series · ⚫ expert opinion
    """
    pt_lower = {p.lower() for p in pub_types}
    if "meta-analysis" in pt_lower:
        return "🟢🟢"  # 1a — meta-analysis
    if "systematic review" in pt_lower:
        return "🟡🟡"  # 2a — systematic review (per report legend grouping)
    if "randomized controlled trial" in pt_lower or "randomised controlled trial" in pt_lower:
        return "🟢"    # 1b — RCT
    if "clinical trial" in pt_lower:
        return "🟡"    # 2b — non-randomised trial
    if "observational study" in pt_lower or "cohort study" in pt_lower:
        return "🟡"    # 2b — cohort / observational
    if "case-control studies" in pt_lower or "case-control study" in pt_lower:
        return "🟠"    # 3 — case-control
    if "case reports" in pt_lower or "case report" in pt_lower:
        return "🔴"    # 4 — case report / series
    if "review" in pt_lower:
        return "⚫"    # 5 — narrative review ≈ expert opinion
    return ""           # Unknown — don't confabulate


def _pubmed_esearch(term: str, max_results: int) -> tuple[list[str], str]:
    """
    Run PubMed esearch. Returns (pmid_list, querytranslation).
    NCBI's Automatic Term Mapping (ATM) expands free-text to MeSH terms.
    """
    params = {"db": "pubmed", "term": term, "retmax": max_results,
              "retmode": "json", "sort": "relevance"}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY

    def _do_esearch():
        _NCBI_LIMITER.wait()
        return requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params=params, timeout=REQUEST_TIMEOUT,
        )
    r = with_retry(_do_esearch, label="pubmed-search")
    r.raise_for_status()
    data = r.json().get("esearchresult", {})
    return data.get("idlist", []), data.get("querytranslation", "")


@cached_search("PubMed")
def tool_pubmed(query: str, max_results: int = RESULTS_PER_SOURCE) -> list[dict]:
    results = []
    log(dim(f"     📚 PubMed ← \"{query[:72]}\""))
    try:
        # Step 1a: esearch — primary query (ATM automatically expands to MeSH)
        ids, translation = _pubmed_esearch(query, max_results)
        if translation and translation.strip().lower() != query.strip().lower():
            log(dim(f"     📚 MeSH: {translation[:80]}"))

        # Step 1b: MeSH supplement — if primary returned less than half requested
        if len(ids) < max_results // 2:
            mesh_query = f"({query})[MeSH Terms] OR ({query})[Title/Abstract]"
            mesh_ids, _ = _pubmed_esearch(mesh_query, max_results)
            # Merge — preserve order of primary results, append new MeSH-only hits
            existing = set(ids)
            for mid in mesh_ids:
                if mid not in existing:
                    ids.append(mid)
                    existing.add(mid)
            if mesh_ids:
                log(dim(f"     📚 MeSH supplement: +{len(mesh_ids)} candidate(s)"))
        if not ids:
            return []

        # Step 2: esummary — get metadata (title, authors, journal, date)
        esummary_params = {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
        if NCBI_API_KEY:
            esummary_params["api_key"] = NCBI_API_KEY

        def _do_esummary():
            _NCBI_LIMITER.wait()
            return requests.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                params=esummary_params,
                timeout=REQUEST_TIMEOUT,
            )
        r2 = with_retry(_do_esummary, label="pubmed-summary")
        r2.raise_for_status()
        summary_data = r2.json().get("result", {})

        # Step 3: efetch — get abstracts + pub types (B.2 + B.3)
        abstracts = _fetch_abstracts(ids)
        time.sleep(0.3)  # NCBI rate limit courtesy pause

        for pmid in ids:
            article      = summary_data.get(pmid, {})
            title        = article.get("title", "Untitled")
            authors_data = article.get("authors", [])
            author_names = []
            for a in authors_data[:3]:
                name = a.get("name", "") if isinstance(a, dict) else str(a)
                if name:
                    author_names.append(name)
            source  = article.get("source", "")
            pubdate = article.get("pubdate", "")
            doi     = article.get("elocationid", "")
            if isinstance(doi, dict):
                doi = doi.get("id", "")

            # B.2: Use abstract if available
            efetch_data  = abstracts.get(pmid, {})
            abstract     = efetch_data.get("abstract", "")
            pub_types    = efetch_data.get("pub_types", [])

            # B.3: Evidence grade from metadata
            evidence_grade = _evidence_grade_from_pub_types(pub_types)

            # Build snippet: abstract preferred, fall back to metadata
            if abstract:
                snippet = abstract[:600]
                if evidence_grade:
                    snippet = f"[{evidence_grade}] " + snippet
                if pub_types:
                    snippet = f"[{', '.join(pub_types[:2])}] " + snippet
            else:
                parts = []
                if author_names: parts.append(f"Authors: {', '.join(author_names)}")
                if source:       parts.append(f"Journal: {source}")
                if pubdate:      parts.append(f"Date: {pubdate}")
                if doi:          parts.append(f"DOI: {doi}")
                snippet = " | ".join(parts)

            results.append({
                "source":         "PubMed",
                "pmid":           pmid,
                "url":            f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "title":          title[:250],
                "snippet":        snippet,
                "doi":            doi,
                "pub_types":      pub_types,
                "evidence_grade": evidence_grade,
            })
        log(dim(f"     📚 → {len(results)} papers"))
        time.sleep(0.3)
    except Exception as e:
        log(yellow(f"     ⚠  PubMed error: {e}"))
    return results

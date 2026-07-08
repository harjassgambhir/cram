"""
search/cochrane.py — Cochrane systematic reviews via PubMed systematic-review filter.

Previous backends removed (both broken as of 2026):
  - rest.cochrane.org: DNS resolution failure on all queries
  - api.nice.org.uk/services/evidence: 404 on all queries

Current approach: PubMed with publication-type filter for systematic reviews.
This reliably returns Cochrane and other high-quality systematic reviews.
"""
import time, requests
from urllib.parse import quote_plus
from cram.config import RESULTS_PER_SOURCE, REQUEST_TIMEOUT, NCBI_API_KEY
from cram.log import log, dim, yellow
from cram.search.base import cached_search


@cached_search("Cochrane")
def tool_cochrane(query: str, max_results: int = RESULTS_PER_SOURCE) -> list[dict]:
    log(dim(f"     🔬 Cochrane ← \"{query[:72]}\""))
    try:
        # PubMed search restricted to systematic reviews (includes Cochrane reviews)
        params = {
            "db": "pubmed",
            "term": f"({query}) AND systematic[filter]",
            "retmax": max_results,
            "retmode": "json",
            "sort": "relevance",
        }
        if NCBI_API_KEY:
            params["api_key"] = NCBI_API_KEY

        r = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            log(dim(f"     🔬 → 0 systematic reviews"))
            return []

        # Fetch summaries
        fetch_r = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
            timeout=REQUEST_TIMEOUT,
        )
        fetch_r.raise_for_status()
        result_data = fetch_r.json().get("result", {})
        results = []
        for pmid in ids:
            item = result_data.get(pmid, {})
            title = item.get("title", "")
            if not title:
                continue
            source_list = item.get("source", "")
            is_cochrane = "cochrane" in source_list.lower()
            label = "[Cochrane Review]" if is_cochrane else "[Systematic Review]"
            authors = item.get("sortfirstauthor", "")
            year = item.get("pubdate", "")[:4]
            results.append({
                "source":  "Cochrane",
                "url":     f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "title":   f"{label} {title[:220]}",
                "snippet": f"{authors} ({year}). {source_list}." if authors else title,
                "pmid":    pmid,
                "year":    year,
            })

        log(dim(f"     🔬 → {len(results)} systematic reviews"))
        time.sleep(0.5)
        return results

    except Exception as e:
        log(yellow(f"     ⚠  Cochrane error: {e}"))
        return []

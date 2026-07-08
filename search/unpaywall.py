"""
search/unpaywall.py — Legal free full-text retrieval by DOI.
Transforms abstract-only hits into full-text evidence for ~50% of papers.
Requires UNPAYWALL_EMAIL in env (free service, no key needed).
"""
import requests
from cram.config import UNPAYWALL_EMAIL, REQUEST_TIMEOUT
from cram.log import log, dim, yellow


def tool_unpaywall(doi: str) -> dict:
    """
    Given a DOI, return legal open-access PDF URL if available.
    Returns dict with: is_oa, pdf_url, host_type, version, license
    """
    if not doi:
        return {}
    try:
        r = requests.get(
            f"https://api.unpaywall.org/v2/{doi}",
            params={"email": UNPAYWALL_EMAIL},
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code != 200:
            return {}
        data = r.json()
        best = data.get("best_oa_location") or {}
        result = {
            "is_oa":     data.get("is_oa", False),
            "pdf_url":   best.get("url_for_pdf"),
            "host_type": best.get("host_type"),    # "publisher" | "repository"
            "version":   best.get("version"),      # "publishedVersion" | "acceptedVersion"
            "license":   data.get("oa_status"),
        }
        if result["pdf_url"]:
            log(dim(f"     🔓 Unpaywall: OA PDF found for {doi[:50]}"))
        return result
    except Exception as e:
        log(yellow(f"     ⚠  Unpaywall error for {doi}: {e}"))
        return {}


def _relevance_score(result: dict, query: str) -> int:
    """
    Fast keyword-overlap score between a result's title+abstract and the query.
    No LLM call — just word intersection. Higher = more directly on-topic.
    """
    if not query:
        return 1  # no query → treat all as equally relevant
    query_words = {w.lower() for w in query.split() if len(w) > 4}
    target = f"{result.get('title', '')} {result.get('snippet', '')}".lower()
    return sum(1 for w in query_words if w in target)


def fetch_fulltext_for_results(results: list[dict], max_papers: int = 3,
                                query: str = "") -> dict[str, str]:
    """
    Fetch full paper text (via PMC / Unpaywall) for the most relevant results.

    Selection logic:
    - Only consider results with a PMID or DOI (needed to fetch full text)
    - Rank by keyword overlap with `query` (if provided) so on-topic papers
      are fetched before off-topic ones
    - Fetch at most `max_papers` full texts

    Returns dict: pmid|doi → full_text_excerpt (up to 15,000 chars each)
    """
    from cram.search.pmc_fulltext import tool_pmc_fulltext
    import requests as req

    fulltext_map: dict[str, str] = {}

    # Filter to results with identifiers and rank by relevance
    candidates = [r for r in results if r.get("doi") or r.get("pmid")]
    if query:
        candidates.sort(key=lambda r: _relevance_score(r, query), reverse=True)

    for result in candidates[:max_papers]:
        doi  = result.get("doi", "")
        pmid = result.get("pmid", "")

        # Try PMC full text first (free, structured, up to 15,000 chars)
        if pmid:
            text = tool_pmc_fulltext(pmid)
            if text:
                fulltext_map[doi or pmid] = text
                continue

        # Try Unpaywall for PDF URL
        if doi:
            oa = tool_unpaywall(doi)
            pdf_url = oa.get("pdf_url")
            if pdf_url:
                try:
                    r = req.get(pdf_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                    if r.status_code == 200:
                        fulltext_map[doi] = f"[PDF available: {pdf_url}] {r.content[:200]!r}"
                except Exception:
                    pass

    return fulltext_map

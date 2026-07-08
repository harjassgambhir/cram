"""search/crossref.py"""
import time, requests
from urllib.parse import quote_plus
from cram.config import RESULTS_PER_SOURCE, REQUEST_TIMEOUT
from cram.log import log, dim, yellow
from cram.provider.openrouter import with_retry
from cram.search.base import cached_search

@cached_search("CrossRef")
def tool_crossref(query: str, max_results: int = RESULTS_PER_SOURCE) -> list[dict]:
    results = []
    log(dim(f"     📖 CrossRef ← \"{query[:72]}\""))
    try:
        clean_q = " ".join(w for w in query.split() if len(w) > 2)[:100]
        r = with_retry(lambda: requests.get(
            f"https://api.crossref.org/works?query={quote_plus(clean_q)}"
            f"&select=title,author,DOI,type,container-title,is-referenced-by-count&rows={max_results}",
            headers={"User-Agent": "CRAM-1/1.0 (mailto:research@cram-agent.local)"},
            timeout=REQUEST_TIMEOUT,
        ), label="crossref")
        if r.status_code >= 400:
            return []
        for item in r.json().get("message", {}).get("items", []):
            titles    = item.get("title", [])
            title     = titles[0] if titles else "Untitled"
            authors   = item.get("author", [])
            author_str= ", ".join(f"{a.get('given','')} {a.get('family','')}".strip()
                                   for a in authors[:3]) if authors else ""
            doi  = item.get("DOI", "")
            url  = item.get("URL", f"https://doi.org/{doi}") if doi else ""
            jrnl = item.get("container-title", [""])[0] if item.get("container-title") else ""
            parts = []
            if author_str: parts.append(f"Authors: {author_str}")
            if jrnl:       parts.append(f"Journal: {jrnl}")
            parts.append(f"Citations: {item.get('is-referenced-by-count', 0)}")
            results.append({
                "source": "CrossRef", "doi": doi, "url": url,
                "title": title[:250], "snippet": " | ".join(parts),
            })
        log(dim(f"     📖 → {len(results)} articles"))
        time.sleep(0.3)
    except Exception as e:
        log(yellow(f"     ⚠  CrossRef error: {e}"))
    return results

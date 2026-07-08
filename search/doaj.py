"""search/doaj.py — Directory of Open Access Journals."""
import requests
from urllib.parse import quote_plus
from cram.config import RESULTS_PER_SOURCE, REQUEST_TIMEOUT
from cram.log import log, dim, yellow
from cram.search.base import cached_search


@cached_search("DOAJ")
def tool_doaj(query: str, max_results: int = RESULTS_PER_SOURCE) -> list[dict]:
    log(dim(f"     📗 DOAJ ← \"{query[:72]}\""))
    results = []
    try:
        r = requests.get(
            f"https://doaj.org/api/search/articles/{quote_plus(query)}",
            params={"pageSize": max_results},
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        for h in r.json().get("results", []):
            bib   = h.get("bibjson", {})
            links = bib.get("link", [{}])
            url   = links[0].get("url", "") if links else ""
            idents = bib.get("identifier", [{}])
            doi    = idents[0].get("id", "") if idents else ""
            results.append({
                "source":  "DOAJ",
                "title":   bib.get("title", "")[:250],
                "url":     url,
                "snippet": bib.get("abstract", "")[:400],
                "doi":     doi,
            })
        log(dim(f"     📗 → {len(results)} articles"))
    except Exception as e:
        log(yellow(f"     ⚠  DOAJ error: {e}"))
    return results

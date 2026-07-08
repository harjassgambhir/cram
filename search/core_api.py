"""search/core_api.py — CORE: 200M+ open-access papers from repositories worldwide."""
import requests
from cram.config import CORE_API_KEY, RESULTS_PER_SOURCE, REQUEST_TIMEOUT
from cram.log import log, dim, yellow
from cram.search.base import cached_search


@cached_search("CORE")
def tool_core(query: str, max_results: int = RESULTS_PER_SOURCE) -> list[dict]:
    if not CORE_API_KEY:
        return []
    log(dim(f"     🌍 CORE ← \"{query[:72]}\""))
    results = []
    try:
        r = requests.get(
            "https://api.core.ac.uk/v3/search/works",
            params={"q": query, "limit": max_results},
            headers={"Authorization": f"Bearer {CORE_API_KEY}"},
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        for item in r.json().get("results", []):
            urls = item.get("sourceFulltextUrls", [])
            url  = item.get("downloadUrl") or (urls[0] if urls else "")
            results.append({
                "source":  "CORE",
                "title":   item.get("title", "")[:250],
                "url":     url,
                "snippet": item.get("abstract", "")[:800],
                "doi":     item.get("doi", ""),
                "year":    str(item.get("yearPublished", "")),
            })
        log(dim(f"     🌍 → {len(results)} works"))
    except Exception as e:
        log(yellow(f"     ⚠  CORE error: {e}"))
    return results

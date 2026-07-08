"""search/open_alex.py"""
import time, requests
from cram.config import RESULTS_PER_SOURCE, REQUEST_TIMEOUT
from cram.log import log, dim, yellow
from cram.provider.openrouter import with_retry
from cram.search.base import cached_search

@cached_search("OpenAlex")
def tool_openalex(query: str, max_results: int = RESULTS_PER_SOURCE) -> list[dict]:
    results = []
    log(dim(f"     📊 OpenAlex ← \"{query[:72]}\""))
    try:
        r = with_retry(lambda: requests.get(
            "https://api.openalex.org/works",
            params={"search": query, "per_page": max_results, "sort": "cited_by_count:desc"},
            timeout=REQUEST_TIMEOUT,
        ), label="openalex")
        r.raise_for_status()
        for work in r.json().get("results", []):
            doi      = work.get("doi", "")
            loc      = (work.get("primary_location") or {})
            src      = (loc.get("source") or {})
            url      = src.get("url", "") or doi or ""
            concepts = work.get("concepts", [])
            topics   = ", ".join(c.get("display_name", "") for c in concepts[:3] if c.get("score", 0) > 0.5)
            parts    = []
            if work.get("publication_year"): parts.append(f"Year: {work['publication_year']}")
            if topics: parts.append(f"Topics: {topics}")
            parts.append(f"Citations: {work.get('cited_by_count', 0)}")
            if (work.get("open_access") or {}).get("is_oa"): parts.append("[OPEN ACCESS]")
            results.append({
                "source": "OpenAlex", "doi": doi, "url": url,
                "title": work.get("title", "Untitled")[:250],
                "snippet": " | ".join(parts),
            })
        log(dim(f"     📊 → {len(results)} works"))
        time.sleep(0.3)
    except Exception as e:
        log(yellow(f"     ⚠  OpenAlex error: {e}"))
    return results

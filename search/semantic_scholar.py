"""search/semantic_scholar.py"""
import time, requests
from cram.config import RESULTS_PER_SOURCE, REQUEST_TIMEOUT
from cram.log import log, dim, yellow
from cram.search.base import cached_search

@cached_search("SemanticScholar")
def tool_semantic_scholar(query: str, max_results: int = RESULTS_PER_SOURCE) -> list[dict]:
    results = []
    log(dim(f"     🧠 SemanticScholar ← \"{query[:72]}\""))
    try:
        time.sleep(1.5)
        r = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": query, "limit": max_results,
                    "fields": "title,authors,year,citationCount,influentialCitationCount,abstract,externalIds,url,venue,journal"},
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code == 429:
            log(yellow("     ⚠  SemanticScholar rate limited"))
            return []
        r.raise_for_status()
        for paper in r.json().get("data", []):
            authors  = ", ".join(a.get("name", "") for a in paper.get("authors", [])[:3])
            abstract = paper.get("abstract", "")
            venue    = paper.get("venue", "") or (paper.get("journal", {}) or {}).get("name", "")
            parts    = []
            if authors:             parts.append(f"Authors: {authors}")
            if paper.get("year"):   parts.append(f"Year: {paper['year']}")
            if venue:               parts.append(f"Venue: {venue}")
            parts.append(f"Citations: {paper.get('citationCount',0)} (influential: {paper.get('influentialCitationCount',0)})")
            if abstract:            parts.append(f"Abstract: {abstract[:800]}")
            results.append({
                "source": "SemanticScholar",
                "doi":   paper.get("externalIds", {}).get("DOI", ""),
                "url":   paper.get("url", ""),
                "title": paper.get("title", "Untitled")[:250],
                "snippet": " | ".join(parts),
            })
        log(dim(f"     🧠 → {len(results)} papers"))
        time.sleep(0.3)
    except Exception as e:
        log(yellow(f"     ⚠  SemanticScholar error: {e}"))
    return results

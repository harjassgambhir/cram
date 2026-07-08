"""search/medrxiv.py"""
import time, requests
from urllib.parse import quote_plus
from cram.config import RESULTS_PER_SOURCE, REQUEST_TIMEOUT
from cram.log import log, dim, yellow
from cram.search.base import cached_search

@cached_search("medRxiv")
def tool_medrxiv(query: str, max_results: int = RESULTS_PER_SOURCE) -> list[dict]:
    results = []
    log(dim(f"     🧬 medRxiv ← \"{query[:72]}\""))
    try:
        clean_q = " ".join(w for w in query.split() if len(w) > 3)[:80]
        r = requests.get(
            f"https://api.biorxiv.org/search/{quote_plus(clean_q)}/0/{max_results}",
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code >= 400:
            return []
        for paper in r.json().get("collection", [])[:max_results]:
            doi   = paper.get("doi", "")
            parts = []
            if paper.get("authors"):  parts.append(f"Authors: {paper['authors'][:150]}")
            if paper.get("date"):     parts.append(f"Date: {paper['date']}")
            if paper.get("category"): parts.append(f"Category: {paper['category']}")
            parts.append("[PREPRINT — not peer-reviewed]")
            if paper.get("abstract"): parts.append(f"Abstract: {paper['abstract'][:400]}")
            server = "medrxiv" if "medrxiv" in doi.lower() else "biorxiv"
            results.append({
                "source": "medRxiv", "doi": doi,
                "url":   f"https://www.{server}.org/content/{doi}v1" if doi else "",
                "title": paper.get("title", "Untitled")[:250],
                "snippet": " | ".join(parts),
            })
        log(dim(f"     🧬 → {len(results)} preprints"))
        time.sleep(0.3)
    except Exception as e:
        log(yellow(f"     ⚠  medRxiv error: {e}"))
    return results

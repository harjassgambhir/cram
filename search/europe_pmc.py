"""search/europe_pmc.py"""
import time, requests
from cram.config import RESULTS_PER_SOURCE, REQUEST_TIMEOUT
from cram.log import log, dim, yellow
from cram.provider.openrouter import with_retry
from cram.search.base import cached_search

@cached_search("EuropePMC")
def tool_europe_pmc(query: str, max_results: int = RESULTS_PER_SOURCE) -> list[dict]:
    results = []
    log(dim(f"     🇪🇺 EuropePMC ← \"{query[:72]}\""))
    try:
        r = with_retry(lambda: requests.get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={"query": query, "format": "json", "resultType": "core",
                    "pageSize": max_results, "sort": "CITED desc"},
            timeout=REQUEST_TIMEOUT,
        ), label="europepmc")
        r.raise_for_status()
        for hit in r.json().get("resultList", {}).get("result", []):
            pmid     = hit.get("pmid", "N/A")
            doi      = hit.get("doi", "")
            is_oa    = hit.get("isOpenAccess", "N") == "Y"
            ftl      = hit.get("fullTextUrlList", {})
            full_url = ftl.get("fullTextUrl", [{}])[0].get("url", "") if ftl else ""
            abstract = hit.get("abstractText", "")
            parts = []
            if hit.get("authorString"): parts.append(f"Authors: {hit['authorString']}")
            if hit.get("journalTitle"): parts.append(f"Journal: {hit['journalTitle']}")
            if hit.get("pubYear"):      parts.append(f"Year: {hit['pubYear']}")
            if is_oa:                   parts.append("[OPEN ACCESS]")
            if abstract:                parts.append(f"Abstract: {abstract[:800]}")
            results.append({
                "source": "EuropePMC", "pmid": pmid, "doi": doi,
                "url":    full_url or f"https://europepmc.org/article/med/{pmid}",
                "title":  hit.get("title", "Untitled")[:250],
                "snippet": " | ".join(parts),
            })
        log(dim(f"     🇪🇺 → {len(results)} articles"))
        time.sleep(0.3)
    except Exception as e:
        log(yellow(f"     ⚠  EuropePMC error: {e}"))
    return results

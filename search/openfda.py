"""
search/openfda.py — FDA drug label lookup via openFDA API.
Structured drug safety data: black box warnings, contraindications, drug interactions.
No API key required (rate-limited to 240 req/min without one).
"""

import requests
from cram.config import REQUEST_TIMEOUT
from cram.log import log, dim, yellow
from cram.search.base import cached_search


@cached_search("OpenFDA")
def tool_openfda(query: str, max_results: int = 5) -> list[dict]:
    """Search FDA drug labels for warnings, interactions, contraindications."""
    log(dim(f"     🏛️ OpenFDA ← \"{query[:72]}\""))
    results = []
    try:
        r = requests.get(
            "https://api.fda.gov/drug/label.json",
            params={"search": f'"{query}"', "limit": max_results},
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code != 200:
            return []
        data = r.json().get("results", [])
        for item in data:
            brand = (item.get("openfda", {}).get("brand_name") or ["Unknown"])[0]
            generic = (item.get("openfda", {}).get("generic_name") or [""])[0]
            warnings = " ".join(item.get("boxed_warning", []))[:500]
            contras = " ".join(item.get("contraindications", []))[:500]
            interactions = " ".join(item.get("drug_interactions", []))[:500]

            snippet_parts = []
            if warnings:
                snippet_parts.append(f"⚠️ BLACK BOX: {warnings[:200]}")
            if contras:
                snippet_parts.append(f"CONTRAINDICATIONS: {contras[:200]}")
            if interactions:
                snippet_parts.append(f"INTERACTIONS: {interactions[:200]}")

            if snippet_parts:
                results.append({
                    "source": "OpenFDA",
                    "url": f"https://api.fda.gov/drug/label.json?search={query}",
                    "title": f"[FDA Label] {brand} ({generic})",
                    "snippet": " | ".join(snippet_parts),
                })
        log(dim(f"     🏛️ → {len(results)} FDA label results"))
    except Exception as e:
        log(yellow(f"     ⚠  OpenFDA error: {e}"))
    return results

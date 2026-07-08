"""search/guidelines.py — NICE, WHO, Medscape clinical guideline search."""
import time, requests
from urllib.parse import quote_plus
from cram.config import RESULTS_PER_SOURCE
from cram.log import log, dim, yellow
from cram.search.base import cached_search


@cached_search("Guidelines")
def tool_medical_guidelines(query: str, max_results: int = RESULTS_PER_SOURCE) -> list[dict]:
    results = []
    log(dim(f"     📋 Guidelines ← \"{query[:72]}\""))
    for site_name, url_tmpl in [
        ("NICE",     "https://www.nice.org.uk/guidance?q={q}"),
        ("WHO",      "https://www.who.int/publications/i/item?search={q}"),
        ("Medscape", "https://emedicine.medscape.com/search?q={q}"),
        ("AIIMS",    "https://www.aiims.edu/index.php/en/search?q={q}"),
        ("ICMR",     "https://main.icmr.gov.in/search/node/{q}"),
    ]:
        try:
            url = url_tmpl.format(q=quote_plus(query))
            r   = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if r.status_code == 200:
                results.append({
                    "source":  site_name,
                    "url":     url,
                    "title":   f"[Guideline] {site_name}: {query}",
                    "snippet": f"Search {site_name} guidelines for: {query}",
                })
            if len(results) >= max_results:
                break
        except Exception:
            continue
    log(dim(f"     📋 → {len(results)} guidelines"))
    time.sleep(0.3)
    return results

"""search/fda_drug.py — FDA drug safety, interactions, contraindications."""
import time
from cram.config import RESULTS_PER_SOURCE
from cram.log import log, dim, yellow
from cram.search.base import cached_search
from cram.search.ddg import DDG_AVAILABLE, DDGS


@cached_search("DrugSafety")
def tool_drug_safety(query: str, max_results: int = RESULTS_PER_SOURCE) -> list[dict]:
    if not DDG_AVAILABLE:
        return []
    results = []
    log(dim(f"     💊 DrugSafety ← \"{query[:72]}\""))
    try:
        time.sleep(2)
        scoped = (
            f"{query} drug interactions contraindications "
            "site:drugs.com OR site:medscape.com OR site:fda.gov OR site:bnf.nice.org.uk"
        )
        with DDGS() as ddgs:
            for r in ddgs.text(scoped, max_results=max_results):
                results.append({
                    "source":  "DrugSafety",
                    "url":     r.get("href", r.get("url", "")),
                    "title":   r.get("title", "")[:250],
                    "snippet": r.get("body", r.get("snippet", ""))[:600],
                })
        log(dim(f"     💊 → {len(results)} drug safety results"))
        time.sleep(0.3)
    except Exception as e:
        log(yellow(f"     ⚠  DrugSafety error: {e}"))
    return results

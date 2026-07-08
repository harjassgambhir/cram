"""search/clinical_trials.py"""
import time, requests
from urllib.parse import quote_plus
from cram.config import RESULTS_PER_SOURCE, REQUEST_TIMEOUT
from cram.log import log, dim, yellow
from cram.provider.openrouter import with_retry
from cram.search.base import cached_search

@cached_search("ClinicalTrials")
def tool_clinical_trials(query: str, max_results: int = RESULTS_PER_SOURCE) -> list[dict]:
    results = []
    log(dim(f"     🏥 ClinicalTrials ← \"{query[:72]}\""))
    try:
        clean_q = " ".join(w for w in query.split() if len(w) > 2)[:100]
        r = with_retry(lambda: requests.get(
            f"https://clinicaltrials.gov/api/v2/studies"
            f"?query.term={quote_plus(clean_q)}&pageSize={max_results}"
            f"&fields=NCTId,BriefTitle,OverallStatus,Condition,BriefSummary",
            timeout=REQUEST_TIMEOUT,
        ), label="clinicaltrials")
        if r.status_code >= 400:
            return []
        for study in r.json().get("studies", [])[:max_results]:
            proto  = study.get("protocolSection", {})
            ident  = proto.get("identificationModule", {})
            status = proto.get("statusModule", {})
            conds  = proto.get("conditionsModule", {}).get("conditions", [])
            summary= proto.get("descriptionModule", {}).get("briefSummary", "")
            nct_id = ident.get("nctId", "")
            parts  = []
            if conds:   parts.append(f"Conditions: {', '.join(conds[:3])}")
            if status.get("overallStatus"): parts.append(f"Status: {status['overallStatus']}")
            if summary: parts.append(f"Summary: {summary[:300]}")
            results.append({
                "source": "ClinicalTrials", "nct_id": nct_id,
                "url":   f"https://clinicaltrials.gov/study/{nct_id}",
                "title": ident.get("briefTitle", ident.get("officialTitle", "Untitled"))[:250],
                "snippet": " | ".join(parts),
            })
        log(dim(f"     🏥 → {len(results)} trials"))
        time.sleep(0.3)
    except Exception as e:
        log(yellow(f"     ⚠  ClinicalTrials error: {e}"))
    return results

"""
search/ctri.py — Clinical Trials Registry India (ctri.nic.in).

CTRI is the ICMR-run registry for all clinical trials conducted in India.
Essential for Indian patient populations — covers trials not on ClinicalTrials.gov.
No API key required. Public search endpoint.
"""
import re, time, requests
from cram.config import RESULTS_PER_SOURCE, REQUEST_TIMEOUT
from cram.log import log, dim, yellow
from cram.search.base import cached_search


@cached_search("CTRI")
def tool_ctri(query: str, max_results: int = RESULTS_PER_SOURCE) -> list[dict]:
    """Search Clinical Trials Registry India for India-specific trial data."""
    log(dim(f"     🇮🇳 CTRI ← \"{query[:72]}\""))
    results = []
    try:
        r = requests.get(
            "https://ctri.nic.in/Clinicaltrials/searchresult.php",
            params={"EncHid": "", "masid": "", "tgid": "",
                    "query": query, "phase": "", "status": ""},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"},
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()

        trial_ids = list(dict.fromkeys(re.findall(r'CTRI/\d{4}/\d{2}/\d{6}', r.text)))
        titles    = re.findall(
            r'<td[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</td>',
            r.text, re.DOTALL | re.IGNORECASE
        )
        clean = re.compile(r'<[^>]+>')

        for i, ctri_id in enumerate(trial_ids[:max_results]):
            title = clean.sub("", titles[i]).strip() if i < len(titles) else query
            results.append({
                "source":  "CTRI",
                "url":     f"https://ctri.nic.in/Clinicaltrials/pmaindet2.php?trialid={ctri_id}",
                "title":   f"[India Trial] {title[:230]}",
                "snippet": f"Clinical Trials Registry India — {ctri_id}",
                "nct_id":  ctri_id,
            })

        log(dim(f"     🇮🇳 → {len(results)} Indian trials"))
        time.sleep(0.5)   # be gentle with government server
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            log(dim(f"     🇮🇳 CTRI → 0 results (endpoint unavailable)"))
        else:
            log(yellow(f"     ⚠  CTRI error: {e}"))
    except Exception as e:
        log(yellow(f"     ⚠  CTRI error: {e}"))

    return results

"""search/brave.py — Brave Search API for web search.
Replaces DDG with a more reliable paid API that doesn't rate-limit aggressively.
"""
import re
import requests
from cram.config import BRAVE_API_KEY, RESULTS_PER_SOURCE, REQUEST_TIMEOUT
from cram.log import log, dim, yellow
from cram.search.base import cached_search

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

_DOI_RE = re.compile(r'doi\.org/(10\.\d{4,}/[^\s?#]+)', re.IGNORECASE)
_PMID_RE = re.compile(r'pubmed\.ncbi\.nlm\.nih\.gov/(\d{7,8})', re.IGNORECASE)

# Trusted medical domains for scoped fallback
DEFAULT_BRAVE_SITES = (
    "site:nejm.org OR site:jamanetwork.com OR site:thelancet.com OR site:bmj.com "
    "OR site:ncbi.nlm.nih.gov OR site:who.int OR site:nice.org.uk OR site:cochrane.org"
)


def _extract_ids(url: str) -> dict:
    ids = {}
    m = _DOI_RE.search(url)
    if m:
        ids["doi"] = m.group(1).rstrip(".,;)")
    m = _PMID_RE.search(url)
    if m:
        ids["pmid"] = m.group(1)
    return ids


@cached_search("Brave")
def tool_brave(query: str, max_results: int = RESULTS_PER_SOURCE,
               trusted_sites: str = DEFAULT_BRAVE_SITES) -> list[dict]:
    """Brave Search API — reliable web search for medical queries."""
    if not BRAVE_API_KEY:
        return []

    results = []
    seen_urls: set[str] = set()
    log(dim(f"     🌐 Brave ← \"{query[:72]}\""))

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": BRAVE_API_KEY,
    }

    def _search(q: str, count: int) -> list[dict]:
        try:
            resp = requests.get(
                BRAVE_SEARCH_URL,
                headers=headers,
                params={"q": q, "count": min(count, 20), "safesearch": "off"},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json().get("web", {}).get("results", [])
        except requests.exceptions.HTTPError as e:
            log(yellow(f"     ⚠  Brave HTTP error: {e}"))
        except requests.exceptions.Timeout:
            log(yellow("     ⚠  Brave timeout"))
        except Exception as e:
            log(yellow(f"     ⚠  Brave error: {e}"))
        return []

    # Pass 1: unscoped — broader results
    for r in _search(query, max_results):
        url = r.get("url", "")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        entry = {
            "source": "Web",
            "url": url,
            "title": r.get("title", "")[:250],
            "snippet": r.get("description", "")[:600],
        }
        ids = _extract_ids(url)
        entry.update(ids)
        results.append(entry)

    # Pass 2: scoped to trusted medical domains
    if trusted_sites and len(results) < max_results:
        for r in _search(f"{query} {trusted_sites}", max_results):
            url = r.get("url", "")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            entry = {
                "source": "Web",
                "url": url,
                "title": r.get("title", "")[:250],
                "snippet": r.get("description", "")[:600],
            }
            ids = _extract_ids(url)
            entry.update(ids)
            results.append(entry)

    log(dim(f"     🌐 → {len(results)} results"))
    return results

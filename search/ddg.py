"""search/ddg.py — DuckDuckGo web search with smart scoping and DOI/PMID extraction."""
import re
import time
import requests
from cram.config import RESULTS_PER_SOURCE
from cram.log import log, dim, yellow
from cram.search.base import cached_search

try:
    from ddgs import DDGS
    DDG_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        DDG_AVAILABLE = True
    except ImportError:
        DDGS = None
        DDG_AVAILABLE = False

# Trusted medical domains for DDG scoping — overridden per field profile
DEFAULT_DDG_SITES = (
    "site:nejm.org OR site:jamanetwork.com OR site:thelancet.com OR site:bmj.com "
    "OR site:ncbi.nlm.nih.gov OR site:uptodate.com OR site:medscape.com "
    "OR site:who.int OR site:medlineplus.gov OR site:nice.org.uk"
)

# Patterns to extract structured identifiers from URLs
_DOI_RE = re.compile(r'doi\.org/(10\.\d{4,}/[^\s?#]+)', re.IGNORECASE)
_PMID_RE = re.compile(r'pubmed\.ncbi\.nlm\.nih\.gov/(\d{7,8})', re.IGNORECASE)
_PMC_RE = re.compile(r'ncbi\.nlm\.nih\.gov/pmc/articles/(PMC\d+)', re.IGNORECASE)


def _extract_ids(url: str) -> dict:
    """Extract DOI, PMID, or PMC ID from a URL."""
    ids = {}
    m = _DOI_RE.search(url)
    if m:
        ids["doi"] = m.group(1).rstrip(".,;)")
    m = _PMID_RE.search(url)
    if m:
        ids["pmid"] = m.group(1)
    m = _PMC_RE.search(url)
    if m:
        ids["pmc_id"] = m.group(1)
    return ids


def _ddg_search(query: str, max_results: int) -> list[dict]:
    """Run a single DDG search and return raw results."""
    with DDGS() as ddgs:
        try:
            return list(ddgs.text(query, max_results=max_results, timelimit="y"))
        except TypeError:
            return list(ddgs.text(query, max_results=max_results))


@cached_search("DDG")
def tool_ddg(query: str, max_results: int = RESULTS_PER_SOURCE,
             trusted_sites: str = DEFAULT_DDG_SITES) -> list[dict]:
    if not DDG_AVAILABLE:
        return []
    results = []
    log(dim(f"     🌐 DDG ← \"{query[:72]}\""))
    try:
        time.sleep(1.5)

        # Strategy: try unscoped first for broader results, then scoped for precision
        # Merge and dedup by URL
        seen_urls = set()
        all_ddg = []

        # Pass 1: unscoped search (broader results)
        try:
            unscoped = _ddg_search(query, max_results=max_results)
            all_ddg.extend(unscoped)
        except Exception:
            pass

        # Pass 2: scoped to trusted medical sites (more precise)
        if trusted_sites:
            time.sleep(1.0)
            try:
                scoped = _ddg_search(f"{query} {trusted_sites}", max_results=max_results)
                all_ddg.extend(scoped)
            except Exception:
                pass

        for r in all_ddg:
            url = r.get("href", r.get("url", ""))
            if url in seen_urls:
                continue
            seen_urls.add(url)

            entry = {
                "source":  "Web",
                "url":     url,
                "title":   r.get("title", "")[:250],
                "snippet": r.get("body", r.get("snippet", ""))[:600],
            }

            # Extract structured IDs from URL
            ids = _extract_ids(url)
            if ids.get("doi"):
                entry["doi"] = ids["doi"]
            if ids.get("pmid"):
                entry["pmid"] = ids["pmid"]

            results.append(entry)

        log(dim(f"     🌐 → {len(results)} results"))
        time.sleep(0.3)
    except Exception as e:
        log(yellow(f"     ⚠  DDG error: {e}"))
    return results

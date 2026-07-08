"""search/exa.py — Exa agentic search engine (exa.ai).
Better relevance than keyword search for medical literature queries.
Includes /contents API for full webpage text extraction.
"""
import requests
from cram.config import EXA_API_KEY, RESULTS_PER_SOURCE, REQUEST_TIMEOUT
from cram.log import log, dim, yellow
from cram.search.base import cached_search

EXA_BASE_URL = "https://api.exa.ai"


@cached_search("Exa")
def tool_exa(query: str, max_results: int = RESULTS_PER_SOURCE) -> list[dict]:
    """Exa agentic search — neural + keyword hybrid for better medical relevance."""
    if not EXA_API_KEY:
        return []

    log(dim(f"     🔎 Exa ← \"{query[:72]}\""))
    results = []

    try:
        response = requests.post(
            f"{EXA_BASE_URL}/search",
            headers={
                "x-api-key": EXA_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "numResults": max_results,
                "type": "auto",
                "useAutoprompt": True,
                "contents": {"text": {"maxCharacters": 1500}},
                "category": "research paper",
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()

        for r in data.get("results", []):
            url = r.get("url", "")
            doi = ""
            if "doi.org/" in url:
                doi = url.split("doi.org/", 1)[1].split("?")[0]
            pmid = ""
            if "pubmed.ncbi.nlm.nih.gov/" in url:
                pmid_part = url.split("pubmed.ncbi.nlm.nih.gov/", 1)[1]
                pmid = pmid_part.strip("/").split("/")[0].split("?")[0]

            # Use highlights if available, fall back to text snippet
            text = r.get("text", "")
            highlights = r.get("highlights", [])
            if highlights:
                snippet = " … ".join(highlights[:3])[:1500]
            else:
                snippet = text[:1500]

            results.append({
                "title": r.get("title", "")[:250],
                "snippet": snippet,
                "url": url,
                "doi": doi,
                "pmid": pmid,
                "source": "Exa",
                "score": r.get("score", 0),
            })

        log(dim(f"     🔎 → {len(results)} results"))

    except requests.exceptions.HTTPError as e:
        log(yellow(f"     ⚠  Exa HTTP error: {e}"))
    except requests.exceptions.Timeout:
        log(yellow("     ⚠  Exa timeout"))
    except Exception as e:
        log(yellow(f"     ⚠  Exa error: {e}"))

    return results


def exa_get_contents(urls: list[str], max_chars: int = 3000) -> dict[str, str]:
    """
    Fetch full webpage text for a list of URLs using Exa /contents API.
    Returns {url: full_text}. Used for post-search enrichment of promising results.
    """
    if not EXA_API_KEY or not urls:
        return {}

    try:
        response = requests.post(
            f"{EXA_BASE_URL}/contents",
            headers={
                "x-api-key": EXA_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "ids": urls[:10],  # API limit
                "text": {"maxCharacters": max_chars},
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return {r["url"]: r.get("text", "") for r in data.get("results", []) if r.get("url")}

    except requests.exceptions.HTTPError as e:
        log(yellow(f"     ⚠  Exa contents HTTP error: {e}"))
    except requests.exceptions.Timeout:
        log(yellow("     ⚠  Exa contents timeout"))
    except Exception as e:
        log(yellow(f"     ⚠  Exa contents error: {e}"))

    return {}

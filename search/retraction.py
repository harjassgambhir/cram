"""search/retraction.py

Retraction / Expression-of-Concern detection.

Two signals, both authoritative and free:

  1. PubMed PublicationType "Retracted Publication" (UI D016441) — already fetched
     by search/pubmed.py for evidence grading, so this costs nothing.

  2. Crossref `updated-by[].type == "retraction"` — this metadata is sourced from
     the Retraction Watch database (visible as `"source": "retraction-watch"` in
     the Crossref record). Covers DOIs from sources other than PubMed.

A retracted paper is not silently dropped — it stays visible but is loudly marked
so the synthesis model, the verifier, and ultimately the doctor all see it. A tool
whose identity is "trustworthy evidence" must never let a retracted trial pass
unflagged.
"""
import time
import requests

from cram.config import REQUEST_TIMEOUT
from cram.log import log, dim, yellow, red
from cram.provider.openrouter import with_retry
from cram.search.base import cached_search

# Loud, greppable markers prepended to title/snippet of flagged results.
RETRACTED_MARKER = "⚠️ RETRACTED"
EOC_MARKER = "⚠️ EXPRESSION OF CONCERN"

# Crossref `updated-by` types we treat as trust-affecting.
_RETRACTION_TYPES = {"retraction"}
_EOC_TYPES = {"expression_of_concern", "expression-of-concern"}

_CROSSREF_HEADERS = {
    "User-Agent": "CRAM-1/1.0 (mailto:research@cram-agent.local)"
}


def is_retracted_pub_type(pub_types) -> bool:
    """True if PubMed PublicationType list marks the article as retracted."""
    if not pub_types:
        return False
    return any("retracted publication" in str(pt).lower() for pt in pub_types)


@cached_search("RetractionCheck")
def _crossref_retraction(doi: str, max_results: int = 1, **kwargs) -> list[dict]:
    """
    Look up a single DOI in Crossref and return [{status, notice_doi, date}] if it
    has been retracted or flagged with an expression of concern, else [].

    Wrapped with @cached_search so each DOI is checked at most once per data dir
    (repeat DOIs across branches/sessions are free).
    """
    doi = (doi or "").strip().lower()
    if not doi:
        return []
    try:
        r = with_retry(lambda: requests.get(
            f"https://api.crossref.org/works/{doi}",
            headers=_CROSSREF_HEADERS,
            timeout=REQUEST_TIMEOUT,
        ), label="crossref-retraction")
        if r.status_code >= 400:
            return []
        msg = r.json().get("message", {}) or {}
        for upd in msg.get("updated-by", []) or []:
            utype = str(upd.get("type", "")).lower()
            date_parts = (upd.get("updated", {}) or {}).get("date-parts", [[None]])
            year = date_parts[0][0] if date_parts and date_parts[0] else None
            if utype in _RETRACTION_TYPES:
                return [{"status": "retracted",
                         "notice_doi": upd.get("DOI", ""),
                         "date": year}]
        # Second pass so a retraction always wins over a softer EoC on the same DOI.
        for upd in msg.get("updated-by", []) or []:
            utype = str(upd.get("type", "")).lower()
            date_parts = (upd.get("updated", {}) or {}).get("date-parts", [[None]])
            year = date_parts[0][0] if date_parts and date_parts[0] else None
            if utype in _EOC_TYPES:
                return [{"status": "concern",
                         "notice_doi": upd.get("DOI", ""),
                         "date": year}]
        return []
    except Exception as e:
        log(dim(f"     ⚠  retraction check failed for {doi}: {e}"))
        return []


def _flag_result(r: dict, status: str, notice_doi: str = "", date=None) -> None:
    """Mutate a result dict in place to mark it retracted / of concern."""
    marker = RETRACTED_MARKER if status == "retracted" else EOC_MARKER
    r["retracted"] = (status == "retracted")
    r["retraction"] = {"status": status, "notice_doi": notice_doi, "date": date}
    # Downgrade evidence grade so grading never elevates a retracted paper.
    r["evidence_grade"] = "⚠️"
    title = r.get("title", "") or ""
    if marker not in title:
        r["title"] = f"{marker}: {title}"
    snippet = r.get("snippet", "") or ""
    if marker not in snippet:
        note = f"[{marker}"
        if date:
            note += f" {date}"
        note += "] "
        r["snippet"] = note + snippet


def annotate_retractions(results: list[dict], crossref_limit: int = 12) -> int:
    """
    Flag retracted / concern papers in `results` (mutated in place).

    - PubMed results are flagged for free from their `pub_types`.
    - Up to `crossref_limit` distinct non-PubMed DOIs are checked against Crossref
      (Retraction Watch). Bounded to keep the pipeline fast; cache makes repeats free.

    Returns the number of results flagged as retracted or of concern.
    """
    flagged = 0
    checked_dois: set[str] = set()
    crossref_budget = crossref_limit

    for r in results:
        if r.get("retracted") or (r.get("retraction") and
                                  r["retraction"].get("status")):
            continue  # already flagged

        # Free signal: PubMed publication type.
        if is_retracted_pub_type(r.get("pub_types")):
            _flag_result(r, "retracted")
            flagged += 1
            continue

        # Crossref / Retraction Watch signal for DOI-bearing, non-PubMed results.
        doi = (r.get("doi") or "").strip().lower()
        if not doi or r.get("source") == "PubMed":
            continue
        if doi in checked_dois:
            continue
        if crossref_budget <= 0:
            continue
        checked_dois.add(doi)
        crossref_budget -= 1
        hits = _crossref_retraction(doi)
        if hits:
            h = hits[0]
            _flag_result(r, h["status"], h.get("notice_doi", ""), h.get("date"))
            flagged += 1

    if flagged:
        log(red(f"     ⚠  retraction check: {flagged} flagged "
                f"(retracted / expression of concern)"))
    return flagged

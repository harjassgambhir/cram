"""
search/pmc_fulltext.py — Free full text from PubMed Central via E-utilities.
Given a PMID, fetches up to 15,000 chars of the full paper, prioritising
Results, Discussion, and Conclusions sections over Introduction.
"""
import re
import requests
from cram.config import REQUEST_TIMEOUT
from cram.log import log, dim, yellow

# Sections worth reading (ordered by clinical priority)
_HIGH_VALUE_SECTIONS = re.compile(
    r"\b(result|finding|outcome|discussion|conclusion|recommendation|"
    r"summary|treatment|management|dose|dosing|regimen|safety|efficacy)\b",
    re.IGNORECASE,
)

_MAX_CHARS = 15_000


def tool_pmc_fulltext(pmid: str) -> str:
    """
    Fetch full text of a PMC paper by PMID.
    Returns up to 15,000 chars, with Results/Discussion prioritised over Introduction.
    """
    if not pmid:
        return ""
    try:
        # Step 1: Convert PMID → PMCID
        r = requests.get(
            "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/",
            params={"ids": pmid, "format": "json"},
            timeout=REQUEST_TIMEOUT,
        )
        records = r.json().get("records", [{}])
        pmcid   = records[0].get("pmcid", "") if records else ""
        if not pmcid:
            return ""

        # Step 2: Fetch full text (plain text — PMC strips most XML noise)
        r2 = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            params={"db": "pmc", "id": pmcid, "rettype": "text", "retmode": "text"},
            timeout=30,
        )
        full_text = r2.text

        # Step 3: Prioritise high-value sections
        # PMC plain text comes as a continuous stream — chunk into ~600-char windows
        # then score each chunk for clinical keyword density.
        chunk_size = 600
        chunks: list[str] = []
        for i in range(0, len(full_text), chunk_size):
            chunk = full_text[i:i + chunk_size].strip()
            if chunk:
                chunks.append(chunk)

        scored: list[tuple[int, str]] = [
            (len(_HIGH_VALUE_SECTIONS.findall(c)), c) for c in chunks
        ]

        # High-scoring chunks first, then low-scoring (to fill budget with context)
        high    = sorted([(s, c) for s, c in scored if s > 0], key=lambda x: -x[0])
        low     = [(s, c) for s, c in scored if s == 0]
        ordered = [c for _, c in high] + [c for _, c in low]

        budget = _MAX_CHARS
        selected: list[str] = []
        for chunk in ordered:
            if budget <= 0:
                break
            selected.append(chunk[:budget])
            budget -= len(chunk)

        text = "\n\n".join(selected)[:_MAX_CHARS]
        log(dim(f"     📄 PMC fulltext: PMID {pmid} → {pmcid} ({len(text):,} chars, "
                f"{len(chunks)} chunks → {len(selected)} selected)"))
        return text
    except Exception as e:
        log(yellow(f"     ⚠  PMC fulltext error for {pmid}: {e}"))
        return ""

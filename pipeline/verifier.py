"""
pipeline/verifier.py — Skeptical finding verification with Layer 3 semantic rescue.
[11] Before REMOVE-ing a finding, do a semantic rescue: ask LLM if any raw result
     actually supports the claim. Prevents false removals from word co-occurrence.
"""

import time
from typing import Optional
from cram.config import VERIFIER_SYSTEM, RATE_LIMIT_SLEEP
from cram.provider.openrouter import llm_json
from cram.memory.store import ResearchMemory
from cram.log import log, dim, green, yellow

# ── Discard tracker — collects findings that didn't pass verification ─────────
# Reset at the start of each run via reset_discarded(). Read via get_discarded().
_discarded_findings: list[dict] = []


def reset_discarded() -> None:
    """Call at start of each research run to clear previous session's discards."""
    global _discarded_findings
    _discarded_findings = []


def get_discarded() -> list[dict]:
    """Return list of discarded findings for the 'Other Directions Explored' section."""
    return list(_discarded_findings)


def _content_tokens(claim: str) -> list[str]:
    """
    Content words used to grep raw results for rescue candidates.
    Keeps long words AND short clinical acronyms (TB, PE, DOAC, ACEi, INR, DKA,
    SGLT2i) — precisely the vocabulary a bare `len(w) > 5` filter would drop.
    """
    toks: list[str] = []
    for raw in claim.split():
        w = raw.strip(".,;:()[]{}\"'")
        if not w:
            continue
        # long content word, or a short token with >=2 uppercase letters (acronym)
        if len(w) > 5 or sum(c.isupper() for c in w) >= 2:
            toks.append(w)
    return toks[:6]


def _semantic_rescue(claim: str, memory: ResearchMemory) -> str:
    """
    Layer 3 semantic rescue: search raw results for any snippet that
    actually supports the specific claim, via an LLM semantic check.

    Returns one of:
      "supported"     — a raw snippet genuinely supports the claim; keep it.
      "unsupported"   — no snippet supports it; stay dropped.
      "rescue-failed" — the rescue LLM errored. FAIL CLOSED: a safety check that
                        cannot run must never resurrect a flagged claim. Caller
                        drops the finding and logs the reason (not silently).
    """
    # Pull candidate snippets from raw results — search for content words
    words = _content_tokens(claim)
    candidate_snippets: list[str] = []
    seen: set[str] = set()

    for term in words:
        hits = memory.grep_raw_results(term)
        for h in hits:
            # h is a dict — use snippet/title fields
            text = h.get("snippet", "") or h.get("title", "")
            key = text[:80]
            if key not in seen:
                seen.add(key)
                candidate_snippets.append(text[:400])
        if len(candidate_snippets) >= 6:
            break

    if not candidate_snippets:
        return "unsupported"

    # Semantic check: does any candidate actually support the claim?
    snippets_text = "\n---\n".join(candidate_snippets[:6])
    prompt = (
        f"Claim: {claim}\n\n"
        f"Source snippets:\n{snippets_text}\n\n"
        "Does ANY of the above snippets directly support this specific claim? "
        "Answer strictly: yes or no.\n"
        'JSON: {"supported": true/false, "reason": "one sentence"}'
    )
    try:
        result = llm_json(
            [{"role": "user", "content": prompt}],
            system="You are a strict evidence checker. Only answer yes if the snippet explicitly supports the claim with specific data.",
            label="rescue check",
            phase="verify",
        )
        return "supported" if bool(result.get("supported", False)) else "unsupported"
    except Exception:
        # FAIL CLOSED. The old behaviour returned bool(candidate_snippets), which
        # resurrected a verifier-flagged claim whenever a keyword grep found any
        # loosely-related snippet — a fail-open hole in the safety checker. An
        # errored rescue must not keep an unverified claim.
        return "rescue-failed"


def verify_findings(findings: list[str], raw_snippets: str,
                    label: str = "", memory: Optional[ResearchMemory] = None) -> list[str]:
    """
    Pass findings through skeptical verifier.
    Each finding is KEEP / WEAKEN / REMOVE.
    WEAKEN is treated as REMOVE — only fully supported claims are kept.
    Before REMOVE: semantic rescue via Layer 3 raw results. If any snippet
    actually supports the claim, override to KEEP.
    """
    if not findings or not raw_snippets.strip():
        return findings

    log(dim(f"  [VERIFY] Skeptical check on {len(findings)} findings..."))
    time.sleep(RATE_LIMIT_SLEEP)

    prompt = (
        "Claimed findings:\n"
        + "\n".join(f"  [{i+1}] {f}" for i, f in enumerate(findings))
        + f"\n\nRaw source snippets:\n{raw_snippets[:3000]}\n\n"
        "For each finding: KEEP, WEAKEN (overstated but has basis), or REMOVE (unsupported).\n"
        "Be conservative — only REMOVE if finding has NO basis in the snippets.\n"
        'JSON: {"verified": [{"original": "...", "action": "KEEP|WEAKEN|REMOVE", '
        '"revised": "...", "reason": "1-line reason", "evidence_grade": "1a|1b|2a|2b|3|4|5|U"}]}'
    )

    try:
        result   = llm_json([{"role": "user", "content": prompt}],
                            system=VERIFIER_SYSTEM, label=f"verify {label}", phase="verify")
        verified = result.get("verified", [])
        kept     = []

        for v in verified:
            action     = v.get("action", "KEEP")
            original   = v.get("original", "")
            revised    = v.get("revised") or original
            grade      = v.get("evidence_grade", "U")
            drop_reason = v.get("reason", action)

            # [11] Before REMOVE/WEAKEN: semantic rescue via Layer 3
            if action in ("REMOVE", "WEAKEN") and memory:
                status = _semantic_rescue(original, memory)
                if status == "supported":
                    log(dim(f"  [VERIFY] L3 semantic rescue: kept — {original[:70]}"))
                    action  = "KEEP"
                    revised = original
                elif status == "rescue-failed":
                    # Fail closed: keep the finding dropped, but record WHY so it
                    # surfaces in "Other Directions Explored" — never silent.
                    drop_reason = "rescue-llm-failure (fail-closed: unverified claim discarded)"
                    log(yellow(f"  [VERIFY] rescue LLM failed — failing closed, dropping: {original[:70]}"))

            if action in ("REMOVE", "WEAKEN"):
                log(yellow(f"  [VERIFY] DROPPED [{action}]: {original[:70]}"))
                _discarded_findings.append({
                    "finding": original[:500],  # display layer handles truncation
                    "reason": drop_reason,
                    "label": label,
                })
            else:
                kept.append(f"{revised} [{grade}]" if grade != "U" else revised)

        log(green(f"  [VERIFY] ✅ {len(kept)}/{len(findings)} findings passed"))
        return kept

    except Exception as e:
        log(yellow(f"  [VERIFY] Skipped ({e}), using unverified"))
        return findings

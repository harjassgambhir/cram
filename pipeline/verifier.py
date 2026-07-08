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


def _semantic_rescue(claim: str, memory: ResearchMemory) -> bool:
    """
    Layer 3 semantic rescue: search raw results for any snippet that
    actually supports the specific claim. Uses LLM semantic check rather
    than loose word matching.
    Returns True if rescue succeeds (claim is supported), False otherwise.
    """
    # Pull candidate snippets from raw results — search for content words
    words = [w for w in claim.split() if len(w) > 5][:4]
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
        return False

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
        return bool(result.get("supported", False))
    except Exception:
        # On LLM failure, fall back to conservative word-match (old behaviour)
        return bool(candidate_snippets)


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
            action   = v.get("action", "KEEP")
            original = v.get("original", "")
            revised  = v.get("revised") or original
            grade    = v.get("evidence_grade", "U")

            # [11] Before REMOVE/WEAKEN: semantic rescue via Layer 3
            if action in ("REMOVE", "WEAKEN") and memory:
                rescued = _semantic_rescue(original, memory)
                if rescued:
                    log(dim(f"  [VERIFY] L3 semantic rescue: kept — {original[:70]}"))
                    action  = "KEEP"
                    revised = original

            if action in ("REMOVE", "WEAKEN"):
                log(yellow(f"  [VERIFY] DROPPED [{action}]: {original[:70]}"))
                _discarded_findings.append({
                    "finding": original[:500],  # display layer handles truncation
                    "reason": v.get("reason", action),
                    "label": label,
                })
            else:
                kept.append(f"{revised} [{grade}]" if grade != "U" else revised)

        log(green(f"  [VERIFY] ✅ {len(kept)}/{len(findings)} findings passed"))
        return kept

    except Exception as e:
        log(yellow(f"  [VERIFY] Skipped ({e}), using unverified"))
        return findings

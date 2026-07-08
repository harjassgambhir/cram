"""
pipeline/contradiction.py — Cross-branch contradiction detection [12].
Runs after all DFS branches complete, before synthesis.
Finds inter-branch conflicts so the synthesiser can resolve them explicitly.
"""

import time
from cram.config import CONTRADICTION_SYSTEM, RATE_LIMIT_SLEEP
from cram.provider.openrouter import llm_json
from cram.log import log, bold, dim, green, yellow, red


def detect_contradictions(all_branches: list[dict]) -> str:
    """
    Pre-synthesis pass: extract key claims per branch, identify contradictions.
    Returns a formatted Markdown section for injection into the synthesis prompt.
    """
    if not all_branches:
        return ""

    log()
    log(bold("╔" + "═" * 58 + "╗"))
    log(bold("║  ⚡  CONTRADICTION DETECTION PASS" + " " * 24 + "║"))
    log(bold("╚" + "═" * 58 + "╝"))

    branch_summaries: list[str] = []
    for b in all_branches:
        findings_text = "\n".join(f"- {f}" for f in b.get("findings", [])[:6])
        if not findings_text:
            findings_text = b.get("consolidated", "")[:800]
        if findings_text:
            branch_summaries.append(
                f"Branch [{b['branch_id']}] — {b['angle']}:\n{findings_text}"
            )

    if not branch_summaries:
        return ""

    prompt = (
        "Analyse these research branch findings for contradictions:\n\n"
        + "\n\n---\n\n".join(branch_summaries)
        + "\n\nIdentify any contradictions between branches "
        "(e.g. different mortality rates, conflicting recommendations, "
        "opposing conclusions for the same clinical question).\n"
        'JSON: {"contradictions": [{"branches": [id1, id2], "topic": "...", '
        '"claim_a": "...", "claim_b": "...", "severity": "HIGH|MEDIUM|LOW", '
        '"recommendation": "how synthesiser should handle this"}]}'
    )

    try:
        result        = llm_json(
            [{"role": "user", "content": prompt}],
            system=CONTRADICTION_SYSTEM,
            label="contradiction detection",
            phase="contradiction",
        )
        contradictions = result.get("contradictions", [])

        if not contradictions:
            log(green("  [CONTRA] No significant contradictions detected"))
            return "\n\n*No significant inter-branch contradictions detected.*\n"

        log(yellow(f"  [CONTRA] {len(contradictions)} contradiction(s) found:"))

        report = "\n\n## ⚡ Inter-Branch Contradictions\n\n"
        for i, c in enumerate(contradictions, 1):
            sev = c.get("severity", "MEDIUM")
            colour = red if sev == "HIGH" else yellow
            log(colour(f"    [{sev}] Branches {c.get('branches',[])} — {c.get('topic','')[:80]}"))
            report += (
                f"**{i}. [{sev}]** Topic: {c.get('topic','')}\n"
                f"- Branches {c.get('branches',[])} disagree\n"
                f"- Claim A: {c.get('claim_a','')}\n"
                f"- Claim B: {c.get('claim_b','')}\n"
                f"- Synthesiser instruction: {c.get('recommendation','')}\n\n"
            )
        return report

    except Exception as e:
        log(yellow(f"  [CONTRA] Detection failed ({e})"))
        return ""

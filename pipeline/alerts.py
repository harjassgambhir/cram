"""
pipeline/alerts.py — Real-time critical alert mechanism (§7).

Classifies every finding as a potential CRITICAL ALERT before the branch continues.
On alert: writes to ALERTS.md immediately, prints to console in red/bold, never waits.
Uses a cheap/fast model (MODEL_ALERT env var) since it runs on every finding.
"""

import time
from cram.config import ALERT_CLASSIFIER_SYSTEM, RATE_LIMIT_SLEEP
from cram.provider.openrouter import llm_json
from cram.memory.store import ResearchMemory
from cram.log import log, bold, red, yellow, dim, stat
from datetime import datetime


def classify_finding(finding: str, patient_profile: str,
                     memory: ResearchMemory = None,
                     context: str = "") -> dict:
    """
    Single-finding alert classifier. Returns the raw classification dict.
    Memory is optional — when None, no ALERTS.md is written (useful for testing).
    context: optional raw source snippet to help the classifier fire on brief findings.
    """
    if not finding or len(finding) < 20:
        return {"is_alert": False, "alert_text": "", "source": ""}

    prompt = (
        f"Finding from research:\n{finding}\n\n"
        f"Patient profile:\n{patient_profile}\n\n"
        + (f"Source context:\n{context[:1500]}\n\n" if context else "")
        + "Is this a CRITICAL ALERT? "
        "A critical alert is ONLY: a black-box warning, a Class I contraindication, "
        "a drug interaction with documented mortality signal, or a guideline that "
        "explicitly states 'do not proceed if [condition present in this patient]'.\n\n"
        "Return ONLY JSON: "
        "{\"is_alert\": true/false, \"alert_text\": \"...\", \"source\": \"...\"}"
    )

    try:
        result = llm_json(
            [{"role": "user", "content": prompt}],
            system=ALERT_CLASSIFIER_SYSTEM,
            label="alert-classifier",
            phase="alert",
        )

        if result.get("is_alert"):
            alert_text   = result.get("alert_text", finding[:200])
            alert_source = result.get("source", "")
            timestamp    = datetime.now().strftime("%H:%M:%S")

            log()
            log(red("  " + "█" * 56))
            log(red(f"  🚨 CRITICAL ALERT [{timestamp}]"))
            log(red(f"  {alert_text}"))
            if alert_source:
                log(red(f"  Source: {alert_source}"))
            log(red("  " + "█" * 56))
            log()

            if memory is not None:
                alert_entry = (
                    f"### 🚨 CRITICAL ALERT [{timestamp}]\n\n"
                    f"**{alert_text}**\n\n"
                    f"Source: {alert_source}\n\n"
                    f"Original finding: {finding[:500]}\n\n"
                    f"---\n"
                )
                memory.write_alerts(alert_entry)
            stat("alerts_fired")

        return result

    except Exception as e:
        log(dim(f"  [ALERT] Classifier failed ({e}) — skipping"))
        return {"is_alert": False, "alert_text": "", "source": ""}


# Keep old name as alias for backward compatibility with dfs.py
def classify_finding_for_alert(finding: str, patient_profile: str,
                                memory: ResearchMemory,
                                context: str = "") -> bool:
    result = classify_finding(finding, patient_profile, memory, context=context)
    return bool(result.get("is_alert"))


def batch_classify_findings(findings: list[str], patient_profile: str,
                             memory: ResearchMemory,
                             context: str = "") -> list[str]:
    """
    Single LLM call to classify all findings in a batch for critical alerts.
    Replaces N per-finding calls with 1 call per depth — ~3–5x fewer LLM calls.
    Falls back to per-finding if batch call fails.
    """
    eligible = [(i, f) for i, f in enumerate(findings) if f and len(f) >= 20]
    if not eligible:
        return findings

    findings_text = "\n".join(f"[{i+1}] {f}" for i, f in enumerate(findings) if f and len(f) >= 20)

    prompt = (
        f"Findings from research:\n{findings_text}\n\n"
        + (f"Patient profile:\n{patient_profile}\n\n" if patient_profile else "")
        + (f"Source context:\n{context[:1200]}\n\n" if context else "")
        + "Which findings (if any) are CRITICAL ALERTS?\n"
        "A critical alert is ONLY: a black-box warning, a Class I contraindication, "
        "a drug interaction with documented mortality signal, or a guideline that "
        "explicitly states 'do not proceed if [condition present in this patient]'.\n\n"
        "Return ONLY JSON: "
        '{"alerts": [{"index": 1, "alert_text": "one sentence", "source": "PMID/URL"}]}'
        " — empty list if none."
    )

    try:
        result = llm_json(
            [{"role": "user", "content": prompt}],
            system=ALERT_CLASSIFIER_SYSTEM,
            label="alert-batch",
            phase="alert",
        )
        alerts = result.get("alerts", []) if isinstance(result, dict) else []
        for alert in alerts:
            idx        = alert.get("index", 0) - 1
            alert_text = alert.get("alert_text", "")
            alert_src  = alert.get("source", "")
            original   = findings[idx] if 0 <= idx < len(findings) else alert_text
            if not alert_text:
                continue
            timestamp = datetime.now().strftime("%H:%M:%S")
            log()
            log(red("  " + "█" * 56))
            log(red(f"  🚨 CRITICAL ALERT [{timestamp}]"))
            log(red(f"  {alert_text}"))
            if alert_src:
                log(red(f"  Source: {alert_src}"))
            log(red("  " + "█" * 56))
            log()
            if memory is not None:
                memory.write_alerts(
                    f"### 🚨 CRITICAL ALERT [{timestamp}]\n\n"
                    f"**{alert_text}**\n\n"
                    f"Source: {alert_src}\n\n"
                    f"Original finding: {original[:500]}\n\n"
                    f"---\n"
                )
            stat("alerts_fired")
        return findings

    except Exception as e:
        log(dim(f"  [ALERT] Batch classifier failed ({e}) — falling back"))
        for finding in findings:
            classify_finding_for_alert(finding, patient_profile, memory, context=context)
            time.sleep(0.05)
        return findings


def format_alerts_section(memory: ResearchMemory) -> str:
    """Read all accumulated alerts and format as the top section of the report."""
    raw = memory.read_alerts()
    if not raw.strip():
        return ""

    return (
        "\n\n"
        "═══════════════════════════════════════════════════════════\n"
        "🚨 CRITICAL ALERTS — READ BEFORE PROCEEDING\n"
        "═══════════════════════════════════════════════════════════\n\n"
        + raw +
        "\n═══════════════════════════════════════════════════════════\n\n"
    )

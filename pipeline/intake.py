"""
pipeline/intake.py — Structured clinical intake and scenario interrogation.
§3.3: Prompt the clinician with a structured intake form before research begins.
Directive §1.1-1.3: Interrogate scenario for missing info, ambiguous terms, invalid terminology.
"""

import sys
from cram.config import INTAKE_SYSTEM
from cram.provider.openrouter import llm, llm_json
from cram.log import log, bold, dim, cyan, yellow, green, red

INTAKE_FORM = """
╔══════════════════════════════════════════════════════════╗
║              CLINICAL INTAKE FORM                       ║
╚══════════════════════════════════════════════════════════╝
  Fill in what you know. Leave blank what you don't.
  Press Enter twice when done.

  Planned procedure / clinical question:
  > {procedure}

  Patient: age, sex, BMI (if relevant):
  > {patient}

  Comorbidities (list each, one per line; blank line to finish):
  > {comorbidities}

  Current medications (with doses if known):
  > {medications}

  Allergies:
  > {allergies}

  Prior surgeries / relevant procedures:
  > {prior}

  Specific concern or question you want answered:
  > {concern}

  Time pressure:
  [1] Routine pre-op / elective planning
  [2] Urgent — need answer within 24h
  [3] Emergency — immediate decision
  > {time_pressure}
"""


def collect_structured_intake() -> dict:
    """Interactive structured intake. Returns dict ready for run_research()."""
    log()
    log(bold("╔" + "═" * 58 + "╗"))
    log(bold("║  📋  CLINICAL INTAKE" + " " * 37 + "║"))
    log(bold("╚" + "═" * 58 + "╝"))
    log(dim("  Answer each prompt. Press Enter to skip a field."))
    log()

    def ask(prompt: str, multiline: bool = False) -> str:
        log(bold(f"  {prompt}"))
        if multiline:
            lines = []
            while True:
                try:
                    line = input("    > ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if not line:
                    break
                lines.append(line)
            return "\n    ".join(lines)
        try:
            return input("    > ").strip()
        except (EOFError, KeyboardInterrupt):
            return ""

    procedure   = ask("Planned procedure / clinical question:")
    patient     = ask("Patient (age, sex, BMI):")
    comorbids   = ask("Comorbidities (Enter each, blank line to finish):", multiline=True)
    medications = ask("Current medications (with doses):", multiline=True)
    allergies   = ask("Allergies:")
    prior       = ask("Prior surgeries / relevant procedures:", multiline=True)
    concern     = ask("Specific concern or question to answer:")
    log(bold("  Time pressure:"))
    log("    1 — Routine pre-op / elective")
    log("    2 — Urgent (24h)")
    log("    3 — Emergency")
    tp_raw = ask("Enter 1, 2, or 3:")
    tp_map = {"1": "routine", "2": "urgent_24h", "3": "emergency"}
    time_pressure = tp_map.get(tp_raw, "routine")

    # Build a rich scenario string for the pipeline
    parts = []
    if procedure:   parts.append(f"Procedure/question: {procedure}")
    if patient:     parts.append(f"Patient: {patient}")
    if comorbids:   parts.append(f"Comorbidities: {comorbids}")
    if medications: parts.append(f"Medications: {medications}")
    if allergies:   parts.append(f"Allergies: {allergies}")
    if prior:       parts.append(f"Prior procedures: {prior}")
    if concern:     parts.append(f"Specific concern: {concern}")
    parts.append(f"Time pressure: {time_pressure}")

    scenario = "\n".join(parts)
    log()
    log(green("  ✅ Intake complete. Building research plan..."))
    return {
        "scenario":      scenario,
        "procedure":     procedure,
        "time_pressure": time_pressure,
    }


def interrogate_scenario(scenario: str) -> str:
    """
    Directive §1.1-1.3: Identify missing info, ambiguous terms, invalid terminology.
    Returns a SCENARIO CLARIFICATIONS block to prepend to the report.
    """
    log(dim("  [INTAKE] Interrogating scenario for assumptions and gaps..."))
    prompt = (
        f"Clinical scenario:\n{scenario}\n\n"
        "Analyse this scenario and identify:\n"
        "1. MISSING information that would materially change the research direction\n"
        "2. AMBIGUOUS terminology with more than one clinical interpretation\n"
        "3. GENUINELY AMBIGUOUS terminology that could change clinical interpretation. "
        "Do NOT flag common typos, formatting variations, or abbreviation differences "
        "(e.g., 'or' instead of '/', missing hyphens, 'Xpert MTB or RIF' instead of "
        "'Xpert MTB/RIF'). Doctors type fast. Interpret charitably and silently correct. "
        "Only flag terms where the ambiguity would genuinely change the research direction.\n"
        "4. UNSTATED ASSUMPTIONS you must make to proceed\n"
        "5. The CLINICAL DECISION this research is intended to support (one sentence)\n"
        "6. The AUDIENCE (who will read this and what they will do with it)\n\n"
        "Return JSON: {"
        '"missing": ["..."], '
        '"ambiguous": [{"term": "...", "interpretations": ["..."]}], '
        '"invalid": ["..."], '
        '"assumptions": ["..."], '
        '"decision": "...", '
        '"audience": "..."'
        "}"
    )
    try:
        result = llm_json(
            [{"role": "user", "content": prompt}],
            system=INTAKE_SYSTEM,
            label="scenario interrogation",
            phase="intake",
        )

        # Keep the block short — doctors don't have time for long preambles.
        # Max 3 assumptions, max 3 missing info items, no ambiguous terms wall.
        body = []

        if result.get("decision"):
            body.append(f"**Interpreted as:** {result['decision']}")
        if result.get("audience"):
            body.append(f"**For:** {result['audience']}\n")

        # Merge assumptions + missing, cap at 5 total
        notes = []
        for a in result.get("assumptions", [])[:3]:
            notes.append(f"- Assumed: {a}")
        for m in result.get("missing", [])[:2]:
            notes.append(f"- Note: {m} not specified — proceeding with best available evidence")
        if notes:
            body.extend(notes)
            body.append("")

        # If interrogation yielded nothing usable, emit no block at all — never a
        # bare "## Scenario Notes" header with no content under it.
        if not body:
            log(dim("  [INTAKE] Interrogation returned no notes — omitting section"))
            return ""

        block = "\n".join(["## Scenario Notes\n"] + body) + "\n---\n\n"
        log(dim(f"  [INTAKE] Interrogation complete — {len(result.get('assumptions',[]))} assumptions, "
                f"{len(result.get('missing',[]))} gaps identified"))
        return block

    except Exception as e:
        log(yellow(f"  [INTAKE] Interrogation failed ({e}) — proceeding without"))
        return ""

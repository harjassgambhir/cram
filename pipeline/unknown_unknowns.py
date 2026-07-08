"""
pipeline/unknown_unknowns.py — The Unknown-Unknown branch [§6].

Runs after all other branches complete, before synthesis.
An adversarial senior clinician asks: "What did we miss?"
Generates 5-8 targeted questions and searches for each.
Findings tagged [UU] in final brief for easy scanning.
"""

import time
from cram.config import UNKNOWN_UNKNOWN_SYSTEM, RATE_LIMIT_SLEEP, DFS_DEPTH
from cram.provider.openrouter import llm, llm_json
from cram.memory.store import ResearchMemory
from cram.log import log, bold, dim, green, yellow, cyan, red
from cram.search.pubmed import tool_pubmed
from cram.search.europe_pmc import tool_europe_pmc
from cram.search.brave import tool_brave


def run_unknown_unknowns(scenario: str, all_branches: list[dict],
                          memory: ResearchMemory,
                          question_analysis: dict | None = None,
                          patient_profile: str = "") -> dict:
    """
    The adversarial gap-finding branch.
    Returns a branch dict compatible with the rest of the pipeline.
    All findings are prefixed [UU] to distinguish them in synthesis.
    """
    log()
    log(bold("╔" + "═" * 58 + "╗"))
    log(bold("║  🔍  UNKNOWN-UNKNOWN BRANCH" + " " * 30 + "║"))
    log(bold("╚" + "═" * 58 + "╝"))
    log(dim("  Adversarial pass: finding what the main branches missed..."))

    # Summarise completed branches for the adversarial prompt
    completed_summary = "\n".join(
        f"- Branch [{b['branch_id']}] {b['angle']}: "
        + (b.get("findings", ["(no findings)"])[0][:100] if b.get("findings") else "(no findings)")
        for b in all_branches
    )

    practitioner_title = (question_analysis or {}).get("practitioner_title", "clinician")
    prompt = (
        f"You are a senior {practitioner_title} reviewing a colleague's research.\n\n"
        f"Clinical scenario:\n{scenario}\n\n"
        f"Research branches already completed:\n{completed_summary}\n\n"
        "Your role is adversarial: find what they missed.\n"
        "Generate 5-8 questions of the form 'Has anyone considered [X]?'\n\n"
        "Focus on:\n"
        "- Drug interactions not explicitly researched\n"
        "- Rare but documented complications for this exact combination of factors\n"
        "- Recent guideline changes (last 24 months) that contradict established practice\n"
        "- Population-specific data that may differ from trial populations "
        "(elderly, renal impairment, Indian patient data)\n"
        "- Things commonly missed in cases of this exact type\n\n"
        'JSON: {"uu_questions": [{"question": "Has anyone considered...", '
        '"priority": "HIGH|MEDIUM|LOW", "search_query": "4-8 word pubmed query"}]}'
    )

    try:
        result   = llm_json(
            [{"role": "user", "content": prompt}],
            system=UNKNOWN_UNKNOWN_SYSTEM,
            label="unknown-unknowns",
            phase="uu",
        )
        questions = result.get("uu_questions", [])
    except Exception as e:
        log(yellow(f"  [UU] Question generation failed ({e})"))
        return _empty_uu_branch()

    if not questions:
        log(dim("  [UU] No additional gaps identified"))
        return _empty_uu_branch()

    log(green(f"  [UU] {len(questions)} gap questions generated:"))
    for q in questions:
        pri = q.get("priority", "")
        marker = "🔴" if pri == "HIGH" else "🟡" if pri == "MEDIUM" else "⚪"
        log(dim(f"    {marker} {q.get('question','')[:100]}"))

    # Search for each question
    all_raw:    list[dict] = []
    uu_findings: list[str] = []

    for q in questions[:6]:  # cap at 6 to control cost
        query = q.get("search_query", "")
        if not query:
            continue

        log(dim(f"  [UU] Searching: \"{query}\""))

        raw: list[dict] = []
        raw.extend(tool_pubmed(query))
        raw.extend(tool_europe_pmc(query))
        raw.extend(tool_brave(query))
        all_raw.extend(raw)

        if raw:
            memory.append_raw_results(raw, query)

        snippets = "\n\n".join(
            f"[{r['source']}] {r.get('title', '')}\n{r.get('snippet', '')}"
            for r in raw[:6]
        )

        if not snippets.strip():
            uu_findings.append(f"[UU] {q['question']} — NO EVIDENCE FOUND in targeted search")
            continue

        try:
            answer = llm(
                [{"role": "user", "content":
                  f"Scenario: {scenario}\n\n"
                  f"Question: {q['question']}\n\n"
                  f"Search results:\n{snippets[:2500]}\n\n"
                  "Answer this specific question using only the search results. "
                  "If the main branches already covered this, say so explicitly. "
                  "If this is a NEWLY IDENTIFIED risk not in the main branches, "
                  "mark it: [NEWLY IDENTIFIED — NOT IN MAIN BRANCHES]\n"
                  "Be specific. Cite sources. Keep under 200 words."}],
                system=(
                    "You answer clinical gap questions from search evidence. "
                    "Be direct and cite sources. Flag new findings clearly."
                ),
                temperature=0.2,
                label=f"UU answer",
                phase="uu",
            )
            uu_findings.append(f"[UU] {q['question']}\n{answer}")
            log(dim(f"  [UU] ✓ answered: {query[:60]}"))
        except Exception as e:
            uu_findings.append(f"[UU] {q['question']} — Search failed: {e}")

    # Write UU branch evidence
    content = (
        f"# Unknown-Unknown Branch [UU]\n"
        f"**Purpose:** Adversarial gap-finding — what the main branches missed\n\n"
        + "\n\n---\n\n".join(uu_findings)
        + f"\n\n---\n*Sources: {len(all_raw)} documents*\n"
    )
    memory.write_branch_evidence("UU", "Unknown Unknowns", content)

    log(green(f"  [UU] ✅ {len(uu_findings)} gap answers generated"))

    return {
        "branch_id":   "UU",
        "angle":       "Unknown Unknowns [adversarial gap-finding]",
        "rationale":   "Adversarial pass to find what main branches missed",
        "raw_results": all_raw,
        "findings":    uu_findings,
        "consolidated":"\n\n".join(uu_findings),
    }


def _empty_uu_branch() -> dict:
    return {
        "branch_id":   "UU",
        "angle":       "Unknown Unknowns",
        "rationale":   "Adversarial gap-finding",
        "raw_results": [],
        "findings":    [],
        "consolidated": "",
    }

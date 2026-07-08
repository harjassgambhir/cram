"""
pipeline/bfs.py — BFS research strategy decomposition and Plan/Build confirmation.
"""

import sys
import time
from cram.config import BFS_BRANCHES, BFS_SYSTEM, RATE_LIMIT_SLEEP
from cram.provider.openrouter import llm_json
from cram.log import log, bold, dim, green, yellow, cyan, red


def bfs_decompose(scenario: str,
                  n: int = BFS_BRANCHES,
                  question_analysis: dict | None = None) -> list[dict]:
    """Decompose scenario into N research branches using field-appropriate strategy."""
    log()
    log(bold("╔" + "═" * 58 + "╗"))
    log(bold("║  BFS PHASE — research strategy decomposition" + " " * 12 + "║"))
    log(bold("╚" + "═" * 58 + "╝"))
    # Use bfs_guidance from question_analyzer if available; no profile instruction injection
    bfs_guidance = question_analysis.get("bfs_guidance", "") if question_analysis else ""
    system = BFS_SYSTEM + (f"\n\nResearch guidance: {bfs_guidance}" if bfs_guidance else "")

    # Intent-aware decomposition: guide branches from question analysis
    intent_block = ""
    if question_analysis and question_analysis.get("key_questions"):
        qtype = question_analysis.get("question_type", "unknown")
        key_qs = question_analysis["key_questions"]
        instructions = question_analysis.get("report_instructions", "")
        intent_block = (
            f"\nQUESTION TYPE: {qtype}\n"
            f"KEY QUESTIONS THE USER WANTS ANSWERED:\n"
            + "\n".join(f"  - {q}" for q in key_qs)
            + "\n\nEach branch MUST map to one or more of these key questions.\n"
            "Do NOT generate generic keyword branches. Generate branches that will "
            "find the specific information the user needs.\n"
        )
        if instructions:
            intent_block += f"\nADDITIONAL GUIDANCE: {instructions}\n"

    prompt = (
        intent_block
        + f"Clinical scenario:\n{scenario}\n\n"
        f"Generate exactly {n} distinct research branches.\n\n"
        "ALL queries: 4-8 word PubMed keyword strings. No full sentences.\n"
        "✓ Good: 'portal hypertension whipple mortality outcomes'\n"
        "✗ Bad:  'What are the outcomes of Whipple in portal hypertension?'\n\n"
        "Return JSON array:\n[\n"
        "  {\"branch_id\": 1,\n"
        "   \"angle\": \"3-5 word label\",\n"
        "   \"rationale\": \"one sentence why this matters for this patient\",\n"
        "   \"primary_query\": \"keyword query\",\n"
        "   \"followup_queries\": [\"q2\", \"q3\"]}\n]"
    )

    branches = llm_json(
        [{"role": "user", "content": prompt}],
        system=system, label="BFS", phase="bfs",
    )

    if isinstance(branches, list):
        log()
        log(green(f"  ✅  {len(branches)} branches planned:"))
        for b in branches:
            log(bold(f"  [{b.get('branch_id','?')}] {b.get('angle','')}"))
            log(dim(f"      {b.get('rationale','')[:100]}"))
            log(dim(f"      Query: {b.get('primary_query','')[:90]}"))

    branches = branches if isinstance(branches, list) else []

    if not branches:
        log()
        log(red("  ❌ BFS returned no branches. LLM may have failed to produce valid JSON."))
        log(yellow("  Retrying BFS with explicit JSON instruction..."))
        retry_prompt = prompt + "\n\nCRITICAL: You MUST return a valid JSON array. No prose."
        branches = llm_json(
            [{"role": "user", "content": retry_prompt}],
            system=system, label="BFS retry", phase="bfs",
        )
        if not isinstance(branches, list):
            branches = []

    return branches


def plan_phase(scenario: str, branches: list[dict],
               auto: bool = False,
               question_analysis: dict | None = None) -> list[dict]:
    """
    [8] Show BFS plan — including proposed report structure — and pause for
    confirmation before DFS starts. Skipped entirely when auto=True (--auto flag).
    """
    if auto:
        return branches

    qa = question_analysis or {}
    output_sections = qa.get("output_sections", [])

    log()
    log(bold("╔" + "═" * 58 + "╗"))
    log(bold("║  📋  PLAN MODE — review before research begins" + " " * 11 + "║"))
    log(bold("╚" + "═" * 58 + "╝"))
    log(f"  Scenario : {scenario[:100]}")

    # Show report structure so the user can see what they'll get
    if output_sections:
        log()
        log(bold("  PROPOSED REPORT STRUCTURE:"))
        for i, s in enumerate(output_sections, 1):
            log(dim(f"    {i:2}. {s}"))
        log()
        log(dim("  (To modify: 'section add <name>'  'section remove N'  'section edit N <name>')"))

    log()
    log(bold("  RESEARCH BRANCHES:"))
    log()
    for b in branches:
        log(f"  [{b.get('branch_id','?')}] {bold(b.get('angle',''))}")
        log(dim(f"       Rationale : {b.get('rationale','')[:90]}"))
        log(dim(f"       Primary Q : {b.get('primary_query','')[:90]}"))
        for i, fq in enumerate(b.get("followup_queries", [])[:2], 1):
            log(dim(f"       Follow-up {i}: {fq[:90]}"))
        log()

    log("  Branch commands:")
    log("    Y / Enter       — proceed with this plan")
    log("    n               — abort")
    log("    skip N          — remove branch N")
    log("    add <topic>     — add a new research direction")
    log("    edit N <desc>   — change branch N's focus")
    log("  Section commands:")
    log("    section add <name>       — add a report section")
    log("    section remove N         — remove section N")
    log("    section edit N <name>    — rename section N")
    log()

    while True:
        try:
            choice = input("  Plan> ").strip()
        except (EOFError, KeyboardInterrupt):
            log("\n  Aborting.")
            sys.exit(0)

        choice_lower = choice.lower()

        if choice_lower in ("", "y", "yes"):
            # Write confirmed sections back to question_analysis so synthesis uses them
            if question_analysis is not None and output_sections:
                question_analysis["output_sections"] = output_sections
            log(green("  ✅ Plan confirmed. Starting research..."))
            return branches
        elif choice_lower in ("n", "no"):
            log("  Research aborted.")
            sys.exit(0)

        # ── Section commands ──────────────────────────────────────────────────
        elif choice_lower.startswith("section add "):
            name = choice[12:].strip()
            if name:
                output_sections.append(name.upper())
                log(green(f"  ✅ Section added: {name.upper()}"))
                _print_sections(output_sections)
            else:
                log("  Usage: section add <section name>")

        elif choice_lower.startswith("section remove "):
            try:
                idx = int(choice_lower.split()[2]) - 1
                if 0 <= idx < len(output_sections):
                    removed = output_sections.pop(idx)
                    log(yellow(f"  Section {idx+1} removed: {removed}"))
                    _print_sections(output_sections)
                else:
                    log(yellow(f"  No section {idx+1}."))
            except (IndexError, ValueError):
                log("  Usage: section remove <number>")

        elif choice_lower.startswith("section edit "):
            parts = choice[13:].strip().split(" ", 1)
            if len(parts) < 2:
                log("  Usage: section edit <number> <new name>")
                continue
            try:
                idx = int(parts[0]) - 1
                if 0 <= idx < len(output_sections):
                    old = output_sections[idx]
                    output_sections[idx] = parts[1].strip().upper()
                    log(green(f"  ✅ Section {idx+1}: '{old}' → '{output_sections[idx]}'"))
                    _print_sections(output_sections)
                else:
                    log(yellow(f"  No section {idx+1}."))
            except (IndexError, ValueError):
                log("  Usage: section edit <number> <new name>")

        # ── Branch commands ───────────────────────────────────────────────────
        elif choice_lower.startswith("skip "):
            try:
                skip_id = int(choice_lower.split()[1])
                branches = [b for b in branches if b.get("branch_id") != skip_id]
                log(yellow(f"  Branch {skip_id} removed. {len(branches)} branches remaining."))
            except (IndexError, ValueError):
                log("  Usage: skip <branch_id>")
        elif choice_lower.startswith("add "):
            user_angle = choice[4:].strip()
            if not user_angle:
                log("  Usage: add <research topic or question>")
                continue
            max_id = max((b.get("branch_id", 0) for b in branches), default=0)
            new_branch = {
                "branch_id": max_id + 1,
                "angle": user_angle[:60],
                "rationale": "User-specified research direction",
                "primary_query": user_angle[:80],
                "followup_queries": [],
            }
            branches.append(new_branch)
            log(green(f"  ✅ Branch {new_branch['branch_id']} added: {user_angle[:80]}"))
        elif choice_lower.startswith("edit "):
            parts = choice[5:].strip().split(" ", 1)
            if len(parts) < 2:
                log("  Usage: edit <branch_id> <new description>")
                continue
            try:
                edit_id = int(parts[0])
                new_desc = parts[1].strip()
                found = False
                for b in branches:
                    if b.get("branch_id") == edit_id:
                        b["angle"] = new_desc[:60]
                        b["primary_query"] = new_desc[:80]
                        b["rationale"] = f"Modified by user: {new_desc[:80]}"
                        found = True
                        log(green(f"  ✅ Branch {edit_id} updated: {new_desc[:80]}"))
                        break
                if not found:
                    log(yellow(f"  Branch {edit_id} not found."))
            except ValueError:
                log("  Usage: edit <branch_id> <new description>")
        else:
            log("  Branch: Y / n / skip N / add <topic> / edit N <desc>")
            log("  Section: section add <name> / section remove N / section edit N <name>")


def _print_sections(sections: list[str]) -> None:
    """Helper to reprint the section list after a modification."""
    log(bold("  Updated report structure:"))
    for i, s in enumerate(sections, 1):
        log(dim(f"    {i:2}. {s}"))

"""
pipeline/synthesis.py — Final synthesis and safety review.
§3.1: New Surgical Brief output format (not academic literature review).
§3.2: Risk tier auto-calculation.
Directive §4.1-4.4: Cross-branch synthesis, unknown unknowns, self-review pass.
"""

import json
import re
import time
from pathlib import Path
from cram.config import (
    SYNTHESIS_SYSTEM, SAFETY_REVIEW_SYSTEM, COMPACTOR_SYSTEM, RATE_LIMIT_SLEEP, INDIA_NOTE
)
from cram.provider.openrouter import llm, llm_json
from cram.memory.store import ResearchMemory
from cram.memory.persistent import PersistentMemory
from cram.pipeline.compactor import compact
from cram.pipeline.alerts import format_alerts_section
from cram.log import log, bold, dim, green, yellow, red, cyan, section


_FORMULARY: dict | None = None

def _load_formulary() -> dict:
    global _FORMULARY
    if _FORMULARY is None:
        path = Path(__file__).parent.parent / "config" / "india_formulary.json"
        try:
            _FORMULARY = json.loads(path.read_text())
        except Exception:
            _FORMULARY = {}
    return _FORMULARY


def _check_india_formulary(scenario: str) -> list[str]:
    """
    Scan the clinical scenario for drugs flagged as unavailable in India.
    Returns list of warning strings to prepend to the report.
    """
    formulary = _load_formulary()
    unavailable = formulary.get("unavailable_notable", {})
    warnings = []
    scenario_lower = scenario.lower()
    for drug, note in unavailable.items():
        if drug.startswith("_"):
            continue
        brands = []
        for category in formulary.values():
            if isinstance(category, dict) and drug in category:
                entry = category[drug]
                brands = entry.get("brands", []) if isinstance(entry, dict) else []
                break
        names_to_check = [drug.replace("_", " ")] + [b.lower() for b in brands]
        if any(name in scenario_lower for name in names_to_check):
            warnings.append(f"🇮🇳 [INDIA FORMULARY] **{drug.replace('_', ' ').title()}**: {note}")
    return warnings


def _build_citation_pool(all_raw: list[dict]) -> set[str]:
    """
    Extract every PMID, DOI, and NCT ID actually found during research.
    Used to verify citations in the synthesised report against real sources.
    """
    pool: set[str] = set()
    for r in all_raw:
        if pmid := (r.get("pmid") or "").strip():
            pool.add(pmid.lower())
        if doi := (r.get("doi") or "").strip():
            pool.add(doi.lower().lstrip("https://doi.org/"))
        if nct := (r.get("nct_id") or "").strip():
            pool.add(nct.lower())
    return pool


def _verify_report_citations(report: str, citation_pool: set[str]) -> str:
    """
    Scan the synthesised report for PMID/DOI/NCT references.
    Any citation NOT found in the actual search results is removed from the report
    (the surrounding sentence is kept but the phantom citation stripped out).
    This is cleaner than tagging — doctors don't need to see [UNVERIFIED] noise.
    """
    if not citation_pool:
        return report

    removed = 0

    def _remover(label: str, group: int = 1, normalize=None):
        def remove(m: re.Match) -> str:
            nonlocal removed
            value = m.group(group).strip().lower()
            if normalize:
                value = normalize(value)
            if value not in citation_pool:
                removed += 1
                return ""   # remove the phantom citation entirely
            return m.group(0)
        return remove

    _doi_norm = lambda d: d.rstrip("⚠️ .,;)").lower().lstrip("https://doi.org/")

    # "PMID: 12345678" and "PMID 12345678"
    report = re.sub(r'\s*PMID[:\s]+(\d{7,8})', _remover("PMID"), report, flags=re.IGNORECASE)
    # "DOI: 10.xxx/yyy" — prefixed form
    report = re.sub(r'\s*DOI[:\s]+(10\.[^\s,;)\]⚠]+)', _remover("DOI", normalize=_doi_norm), report, flags=re.IGNORECASE)
    # Bare DOI in parentheses or brackets: (10.xxx/yyy) or [10.xxx/yyy]
    report = re.sub(r'[\(\[](10\.\d{4,}[^\s,;)\]⚠]{3,})[\)\]⚠ ]*', _remover("DOI", normalize=_doi_norm), report)
    # NCT IDs
    report = re.sub(r'\s*(NCT\d{8})', _remover("NCT"), report, flags=re.IGNORECASE)

    if removed:
        log(yellow(f"  [CITE-VERIFY] Removed {removed} unverified citation(s) from report"))
    else:
        log(dim("  [CITE-VERIFY] ✅ All citations verified"))

    return _clean_citation_artifacts(report)


def _clean_citation_artifacts(report: str) -> str:
    """
    Tidy citation debris so reports don't look sloppy to a clinician.
    Removes empty brackets left by citation stripping, 'DOI: N/A' noise, and
    dangling commas inside parentheses (e.g. '(2026,)' → '(2026)').
    """
    subs = [
        (r"\(\s*(?:DOI|PMID|NCT)\s*[:#]?\s*(?:N/?A|none|n/a|—|-)?\s*\)", ""),   # (DOI: N/A), (PMID: )
        (r"\[\s*(?:DOI|PMID|NCT)\s*[:#]?\s*\]", ""),                            # [PMID: ]
        (r"\[\s*\]", ""),                                                        # empty []
        (r"\(\s*\)", ""),                                                        # empty ()
        (r",[ \t]*\)", ")"),                                                     # (2026,) → (2026)
        (r"\([ \t]*,[ \t]*", "("),                                               # (, x → (x
        (r"[ \t]+([.,;:])", r"\1"),                                              # space before punctuation (not newlines)
        (r"[ \t]{2,}", " "),                                                     # collapse runs of spaces
    ]
    cleaned = 0
    for pattern, repl in subs:
        report, n = re.subn(pattern, repl, report)
        cleaned += n
    if cleaned:
        log(dim(f"  [CITE-VERIFY] Cleaned {cleaned} citation artifact(s)"))
    return report


# ── §3.2 Risk tier ──────────────────────────────────────────────────────────────

def calculate_risk_tier(scenario: str, all_branches: list[dict]) -> str:
    """
    Auto-calculate risk tier (HIGH/MODERATE/STANDARD) from scenario and evidence.
    The big model determines risk dynamically — no rigid profile-specific criteria.
    """
    log(dim("  [SYNTHESIS] Calculating risk tier..."))
    evidence_snippet = "\n".join(
        f"- {f[:100]}"
        for b in all_branches
        for f in b.get("findings", [])[:2]
    )[:1500]

    prompt = (
        f"Clinical scenario:\n{scenario}\n\n"
        f"Key evidence:\n{evidence_snippet}\n\n"
        "Assess clinical risk based on the scenario and evidence above.\n"
        "Consider: severity of condition, proposed intervention, contraindications found, "
        "comorbidities, and evidence quality.\n\n"
        "Return JSON: {\"tier\": \"HIGH|MODERATE|STANDARD\", \"justification\": \"one sentence\"}"
    )

    try:
        result = llm_json(
            [{"role": "user", "content": prompt}],
            system="You calculate clinical risk tiers. Return only JSON.",
            label="risk tier",
            phase="synthesis",
        )
        tier    = result.get("tier", "UNKNOWN")
        justify = result.get("justification", "")
        colour  = red if tier == "HIGH" else yellow if tier == "MODERATE" else green
        log(colour(f"  [RISK] Tier: {tier} — {justify}"))
        return f"**RISK TIER: {tier}** — {justify}"
    except Exception as e:
        log(yellow(f"  [SYNTHESIS] Risk tier failed ({e})"))
        return "**RISK TIER: UNKNOWN** — automated calculation failed"


# ── Main synthesis ──────────────────────────────────────────────────────────────

def synthesize_report(
    scenario: str,
    all_branches: list[dict],
    memory: ResearchMemory,
    persistent_mem: PersistentMemory,
    contradiction_report: str = "",
    interrogation_block: str = "",
    patient_profile: str = "",
    question_analysis: dict | None = None,
) -> tuple[str, list[dict], str, bool]:
    section("SYNTHESIS PHASE")

    # Risk tier
    risk_tier = calculate_risk_tier(scenario, all_branches)

    # Persistent context
    persistent_block = persistent_mem.format_for_prompt(field="general")
    index_snapshot   = memory.read_index()

    # Collect each branch's evidence — no per-branch compaction (damages DOIs/PMIDs)
    evidence_sections: list[str] = []
    all_raw: list[dict] = []
    for branch in all_branches:
        bid     = branch.get("branch_id", "?")
        angle   = branch.get("angle", "")
        content = memory.read_branch_evidence(bid) or branch.get("consolidated", "")
        evidence_sections.append(f"## [{bid}] {angle}\n{content}")
        all_raw.extend(branch.get("raw_results", []))

    evidence_digest = "\n\n---\n\n".join(evidence_sections)
    if len(evidence_digest) > 60000:
        evidence_digest = compact(evidence_digest, label="full digest", min_chars=50000)

    # Build citation pool from every source actually found during research
    citation_pool = _build_citation_pool(all_raw)

    # India formulary check — flag unavailable drugs before synthesis
    formulary_warnings = _check_india_formulary(scenario)
    if formulary_warnings:
        log(yellow(f"  [FORMULARY] 🇮🇳 {len(formulary_warnings)} India availability flag(s)"))
        for w in formulary_warnings:
            log(yellow(f"    {w[:100]}"))

    # Alerts section (always at top)
    alerts_section = format_alerts_section(memory)

    # Dynamic context block (§3 / §18 split)
    dynamic_ctx = ""
    if persistent_block:  dynamic_ctx += f"\nPERSISTENT CONTEXT:\n{persistent_block}\n"
    if contradiction_report: dynamic_ctx += f"\nKNOWN CONTRADICTIONS:\n{contradiction_report}\n"
    if patient_profile:   dynamic_ctx += f"\nPATIENT PROFILE:\n{patient_profile}\n"
    if formulary_warnings:
        dynamic_ctx += "\nINDIA FORMULARY ALERTS:\n" + "\n".join(formulary_warnings) + "\n"

    # Dynamic output structure — question analysis overrides profile defaults
    qa = question_analysis or {}
    output_sections = qa.get("output_sections") or [
        "OVERVIEW", "KEY FINDINGS", "EVIDENCE SUMMARY", "EVIDENCE GAPS", "SOURCES"
    ]

    sections_list = "\n".join(f"{i+1}. **{s}**" for i, s in enumerate(output_sections))

    # Build question-aware instructions
    question_context = ""
    if qa.get("key_questions"):
        question_context = (
            "\n\nKEY QUESTIONS TO ANSWER (the user specifically wants these addressed):\n"
            + "\n".join(f"  - {q}" for q in qa["key_questions"])
            + "\n\nEvery key question above MUST be addressed in the report. "
            "If evidence was not found for a question, state that explicitly.\n"
        )
    if qa.get("report_instructions"):
        question_context += f"\nREPORT GUIDANCE: {qa['report_instructions']}\n"

    # Build synthesis system: use question_analyzer guidance; fully dynamic
    synthesis_guidance = qa.get("synthesis_guidance", "")
    system = SYNTHESIS_SYSTEM
    if synthesis_guidance:
        system += f"\n\nSynthesis guidance: {synthesis_guidance}\n"
    system += f"\n{INDIA_NOTE}"

    prompt = (
        f"CLINICAL SCENARIO:\n{scenario}{dynamic_ctx}\n\n"
        f"RISK TIER: {risk_tier}\n\n"
        f"RESEARCH INDEX:\n{index_snapshot}\n\n"
        f"CONSOLIDATED EVIDENCE:\n{evidence_digest}\n\n"
        + question_context +
        f"\nWrite a clinical brief that answers the user's specific questions. "
        f"Use this structure (adapt section content to match the actual question):\n\n{sections_list}\n\n"
        "Format rules:\n"
        "- If the report includes a CRITICAL ALERTS section: any finding that could cause "
        "death or serious harm if missed. State IMMEDIATELY and ACTION-ORIENTED. "
        "If none, write 'No critical alerts identified.'\n"
        "- Every bullet point must have a citation (PMID/DOI/NCT/URL) — ONLY cite sources "
        "that appear in the consolidated evidence above. Do NOT invent PMIDs or DOIs. "
        "If no verifiable source exists for a claim: either REMOVE the claim if it adds "
        "no clinical value, OR mark it explicitly as ⚫ [Expert Opinion] and strip any "
        "specific numbers/percentages. Never state a specific figure without a citation. "
        "Never use '[§ from agent memory]' as a citation.\n"
        "- Evidence grade after every claim: 🟢🟢/🟢/🟡🟡/🟡/🟠/🔴/⚫/⚠️\n"
        "- EVIDENCE GAPS: state explicitly as 'NO EVIDENCE FOUND for: [question]'\n"
        "- [UU] tagged findings in UNKNOWN UNKNOWNS section if present\n"
        "- India-specific data flagged with 🇮🇳 where found\n\n"
        "⚠️ = HIGH RISK | ✅ = strong evidence | ⚡ = weak evidence"
    )

    # Inject the FULL citation pool so the model can only cite real sources.
    # Split by type for readability — model is more accurate when IDs are grouped.
    if citation_pool:
        pmids = sorted(i for i in citation_pool if i.isdigit())
        dois  = sorted(i for i in citation_pool if i.startswith("10."))
        ncts  = sorted(i for i in citation_pool if i.startswith("nct"))
        pool_lines = []
        if pmids:
            pool_lines.append("PMIDs: " + ", ".join(pmids))
        if dois:
            pool_lines.append("DOIs: " + ", ".join(dois))
        if ncts:
            pool_lines.append("NCT IDs: " + ", ".join(ncts))
        pool_hint = (
            "\n\nVERIFIABLE CITATION POOL — this is the COMPLETE list of sources retrieved "
            "during research. You may ONLY cite IDs from this list. Any ID not here was never "
            "retrieved and does not exist in the evidence pool. Hallucinating a citation is "
            "more dangerous than marking a claim as ⚫ [Expert Opinion].\n"
            + "\n".join(pool_lines)
            + "\n"
        )
        prompt += pool_hint

    log(dim(f"  Synthesising {len(all_branches)} branches, {len(all_raw)} sources..."))

    report = llm(
        [{"role": "user", "content": prompt}],
        system=system,
        temperature=0.1,
        label="final synthesis",
        phase="synthesis",
    )

    log(green(f"  ✅ Report generated ({len(report):,} chars)"))

    # Citation verification — flag any PMID/DOI/NCT not in actual search results
    report = _verify_report_citations(report, citation_pool)

    # Fix bare mermaid blocks not wrapped in code fences
    report = _fix_mermaid_fences(report)

    # Combined review pass (self-review + safety in one LLM call)
    report, safety_section, ready = _combined_review_pass(report, scenario, all_raw)

    # If review found issues: correct, re-check, and if issues persist apply one
    # final correction so the shipped report never contradicts its own safety
    # section (e.g. a flagged claim the reviewer said to delete but is still present).
    if not ready:
        report, safety_section, ready = _correction_pass(report, safety_section, scenario)
        # Re-verify once — catches anything the correction missed or introduced
        report, safety_section, ready = _combined_review_pass(report, scenario, all_raw)
        if not ready:
            log(yellow("  [REVIEW] Residual issues — applying final targeted correction"))
            # Bounded: trust this pass, no third review (avoids cost blow-up / loops)
            report, safety_section, ready = _correction_pass(report, safety_section, scenario)

    return alerts_section + report, all_raw, safety_section, ready


def _fix_mermaid_fences(report: str) -> str:
    """Wrap bare mermaid blocks (written without code fences) in proper ```mermaid fences."""
    # Match: line containing only 'mermaid', followed by diagram lines, until a blank line or ##
    def wrap(m: re.Match) -> str:
        content = m.group(1).rstrip()
        return f"```mermaid\n{content}\n```"
    return re.sub(
        r"(?m)^mermaid\s*\n((?:(?!```|^##|^\s*$).+\n?)+)",
        wrap,
        report,
    )


def _correction_pass(
    report: str, safety_section: str, scenario: str
) -> tuple[str, str, bool]:
    """
    Given a report that failed the safety review, fix each flagged issue per its
    recommendation. Returns a corrected report, updated safety section, and ready=True.
    """
    section("CORRECTION PASS")

    # Extract issues from safety section text
    issue_lines = [
        line.strip()
        for line in safety_section.splitlines()
        if line.strip().startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."))
        or line.strip().startswith("→")
    ]
    if not issue_lines:
        log(yellow("  [CORRECTION] No parseable issues — skipping"))
        return report, safety_section, True

    issues_text = "\n".join(issue_lines)
    log(dim(f"  Fixing {issues_text.count(chr(10))//2 + 1} issue(s)..."))

    prompt = (
        f"Scenario: {scenario}\n\n"
        f"The following clinical report has been reviewed and found to contain issues.\n"
        f"Fix ONLY the issues listed. Do NOT change anything else — preserve all citations, "
        f"evidence grades (🟢🟢/🟢/⚫/🟡 etc.), section headings, tables, and clinical content.\n\n"
        f"ISSUES TO FIX:\n{issues_text}\n\n"
        f"REPORT:\n{report}\n\n"
        f"Return ONLY the corrected report text. No commentary, no preamble."
    )

    try:
        corrected = llm(
            [{"role": "user", "content": prompt}],
            system=(
                "You are a clinical editor making targeted corrections to a research brief. "
                "Fix only what is listed. Preserve all structure, citations, and evidence grades exactly."
            ),
            label="correction pass",
            phase="safety",
            temperature=0.0,
        )

        # Sanity check: corrected must be at least 70% of original length
        if len(corrected) < len(report) * 0.7:
            log(yellow("  [CORRECTION] LLM shrunk report — keeping original"))
            corrected = report

        # Replace the NOT READY banner if present
        corrected = corrected.replace(
            "> 🚨 **SAFETY REVIEW: NOT READY FOR CLINICAL USE**\n"
            "> The automated safety review identified issues that must be resolved.\n"
            "> See the Safety Review section at the bottom of this report.\n"
            "> Do NOT use this report for clinical decisions until issues are addressed.\n",
            "",
        )

        # Extract only the numbered issue lines from the old safety section
        issue_entries = "\n".join(
            line for line in safety_section.splitlines()
            if re.match(r"^\d+\.", line.strip()) or line.strip().startswith("→")
        )
        updated_safety = (
            "\n\n---\n\n## 🛡️ Safety Review\n\n"
            "**Ready for Clinical Reference:** Yes — issues found and corrected\n\n"
            "The following issues were identified and corrected automatically:\n\n"
            + issue_entries
        )

        log(green("  [CORRECTION] ✅ Report corrected and ready"))
        return corrected, updated_safety, True

    except Exception as e:
        log(yellow(f"  [CORRECTION] Failed ({e}) — keeping original with issues flagged"))
        return report, safety_section, False


def _combined_review_pass(
    report: str, scenario: str, all_raw: list[dict]
) -> tuple[str, str, bool]:
    """
    Single LLM call replacing the separate self-review + safety review passes.

    Returns:
        - report text with inline markers added
        - safety section string to append
        - ready_for_clinical_use bool
    """
    section("REVIEW PASS")
    log(dim(f"  Reviewing report ({len(report):,} chars, {len(all_raw)} sources)..."))

    # Cap at 16k chars — large reports cause response truncation on the review pass
    review_text = report[:16000] if len(report) > 16000 else report

    prompt = (
        f"Scenario: {scenario}\n\n"
        f"Report:\n{review_text}\n\n"
        "## TASK\n"
        "Do two things in a single pass:\n\n"
        "### 1. Inline markers (add directly into the report text)\n"
        "Add ONLY these markers — use sparingly, only where truly needed:\n"
        "- [UNSUPPORTED] — ONLY for specific numerical claims (%, OR, sensitivity, mortality) "
        "stated as fact WITHOUT any citation. Do NOT add for general clinical principles, "
        "standard of care knowledge, or anything labelled 'expert consensus'.\n"
        "- [CONTRADICTION] — claim directly contradicts another in the same report\n"
        "- ⁇ — potentially hallucinated or misattributed PMID/DOI (format looks invented). "
        "Use ⁇ for this — NEVER ⚠️, which is reserved for HIGH clinical risk.\n"
        "Do NOT rewrite sentences. Do NOT add markers for style issues or uncited standard clinical knowledge.\n\n"
        "### 2. Safety issues (structured, appended after the report)\n"
        "Identify ONLY genuine patient-harm risks:\n"
        "- Drug interactions with mortality signals not addressed\n"
        "- Contraindications to proposed treatment not flagged\n"
        "- Missing standard-of-care alternatives that change management\n"
        "- Dangerously incorrect clinical claims\n\n"
        "DO NOT flag: citation formatting, methodology, informational gaps, "
        "plausible but imperfectly cited claims.\n\n"
        "## RESPONSE FORMAT\n"
        "Return JSON:\n"
        '{"report": "<full report text with inline markers>", '
        '"safety_issues": [{"type": "DRUG_INTERACTION|CONTRAINDICATION|MISSING_SOC|DANGEROUS_CLAIM", '
        '"description": "one concise sentence", "severity": "CRITICAL|HIGH", '
        '"recommendation": "one action sentence"}], '
        '"ready_for_clinical_use": true|false}\n\n'
        "AT MOST 10 safety issues. Empty list if none."
    )

    # Retry once with shorter context if first attempt fails
    _result = None
    for _attempt, _chars in enumerate([len(review_text), 10000]):
        if _attempt == 1:
            log(yellow("  [REVIEW] Retrying with shorter context..."))
            short_text = report[:_chars]
            prompt = prompt.replace(review_text, short_text)
        try:
            _result = llm_json(
                [{"role": "user", "content": prompt}],
                system=(
                    "You are a senior clinical editor. Review clinical research reports for inline "
                    "quality issues and genuine patient-safety concerns. Be precise and conservative — "
                    "flag only real problems. Return ONLY JSON."
                    "\n\n" + SAFETY_REVIEW_SYSTEM
                ),
                label="combined review",
                phase="safety",
                temperature=0.1,
            )
            break
        except Exception as e:
            if _attempt == 0:
                log(yellow(f"  [REVIEW] Attempt 1 failed ({e}) — retrying"))
                continue
            log(yellow(f"  [REVIEW] Failed ({e}) — skipping review"))
            return (
                report,
                "\n\n---\n\n## 🛡️ Safety Review\n\n"
                "⚠️ Automated safety review could not be completed. "
                "Verify all claims before clinical use.\n",
                True,
            )

    # llm_json may return a list if the model emits a JSON array — never let that
    # crash a 15-minute run. Coerce to dict (empty → ship report as-is, ready).
    result = _result if isinstance(_result, dict) else {}
    reviewed_report = result.get("report", "") or report
    # Sanity check: if LLM returned something much shorter, it rewrote — keep original
    _report_shrunk = False
    if len(reviewed_report) < len(report) * 0.7:
        log(yellow("  [REVIEW] LLM shrunk report — keeping original, markers lost"))
        reviewed_report = report
        _report_shrunk = True

    issues = result.get("safety_issues", [])[:10]
    ready  = result.get("ready_for_clinical_use", True)
    # If we discarded the LLM's rewrite and there are no flagged issues, treat as ready
    if _report_shrunk and not issues:
        ready = True

    critical = [i for i in issues if i.get("severity") == "CRITICAL"]
    high     = [i for i in issues if i.get("severity") == "HIGH"]
    log(yellow(f"  {len(issues)} safety issues ({len(critical)} critical, {len(high)} high)"))
    for issue in issues:
        sev = issue.get("severity", "")
        msg = issue.get("description", "")[:120]
        if sev == "CRITICAL":  log(red(f"    🚨 CRITICAL: {msg}"))
        elif sev == "HIGH":    log(yellow(f"    ⚠️  HIGH: {msg}"))
    log(green(f"  Ready: {'YES' if ready else 'NO'}"))

    if not issues:
        safety_section = "\n\n---\n\n## 🛡️ Safety Review\n\n✅ No critical safety concerns identified.\n"
    else:
        safety_section  = "\n\n---\n\n## 🛡️ Safety Review\n\n"
        safety_section += f"**Ready for Clinical Reference:** {'Yes' if ready else 'No — see issues below'}\n\n"
        for i, issue in enumerate(issues, 1):
            safety_section += (
                f"{i}. **[{issue.get('severity','')}]** {issue.get('description','')}\n"
                f"   → {issue.get('recommendation','')}\n\n"
            )

    log(green("  [REVIEW] ✅ Combined review complete"))
    return reviewed_report, safety_section, ready


# Keep as alias so run.py can still call safety_review() for the return value
def safety_review(report: str, scenario: str, all_raw: list[dict]) -> tuple[str, bool]:
    """Kept for backward compatibility. Combined review now runs inside synthesize_report."""
    return "", True

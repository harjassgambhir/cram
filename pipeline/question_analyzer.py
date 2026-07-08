"""
pipeline/question_analyzer.py — Dynamic question understanding.
Determines what TYPE of question the user asked and what output structure
the report should use. Runs with the big model (Tier 1) before BFS.
"""

from cram.config import QUESTION_ANALYSIS_SYSTEM
from cram.provider.openrouter import llm_json
from cram.log import log, bold, dim, green, yellow


# ── Default output sections by question type ─────────────────────────────────

DEFAULT_SECTIONS = {
    "pre_op": [
        "CRITICAL ALERTS",
        "PATIENT PROFILE SUMMARY",
        "RISK TIER",
        "PRE-OP (72h before)",
        "ANAESTHESIA BRIEF",
        "INTRAOPERATIVE MODIFICATIONS",
        "POST-OP MANAGEMENT",
        "TEAM BRIEFING POINTS",
        "EVIDENCE GAPS",
        "UNKNOWN UNKNOWNS",
        "SOURCES",
    ],
    "research_design": [
        "RESEARCH QUESTION ANALYSIS",
        "PRIOR ART — EXISTING SIMILAR STUDIES",
        "STUDY DESIGN RECOMMENDATIONS",
        "PARAMETERS AND ENDPOINTS TO MEASURE",
        "CLINICAL FINDINGS TO CORRELATE",
        "SAMPLE SIZE AND STATISTICAL CONSIDERATIONS",
        "POTENTIAL PITFALLS AND LIMITATIONS",
        "EVIDENCE GAPS THIS STUDY COULD FILL",
        "KEY REFERENCES",
        "SOURCES",
    ],
    "literature_review": [
        "TOPIC OVERVIEW",
        "CURRENT EVIDENCE SUMMARY",
        "SYSTEMATIC REVIEWS AND META-ANALYSES",
        "KEY CLINICAL TRIALS",
        "GUIDELINES AND CONSENSUS STATEMENTS",
        "CONTROVERSIES AND CONFLICTING EVIDENCE",
        "RECENT DEVELOPMENTS (LAST 2 YEARS)",
        "EVIDENCE GAPS",
        "CLINICAL IMPLICATIONS",
        "SOURCES",
    ],
    "clinical_comparison": [
        "COMPARISON OVERVIEW",
        "APPROACH A — EVIDENCE SUMMARY",
        "APPROACH B — EVIDENCE SUMMARY",
        "HEAD-TO-HEAD COMPARISONS",
        "OUTCOMES AND EFFECTIVENESS",
        "SAFETY AND ADVERSE EVENTS",
        "COST AND FEASIBILITY CONSIDERATIONS",
        "GUIDELINE RECOMMENDATIONS",
        "EVIDENCE GAPS",
        "SOURCES",
    ],
    "case_discussion": [
        "CLINICAL PRESENTATION ANALYSIS",
        "DIFFERENTIAL DIAGNOSIS",
        "DIAGNOSTIC WORKUP",
        "MANAGEMENT OPTIONS",
        "EVIDENCE-BASED RECOMMENDATIONS",
        "MONITORING AND FOLLOW-UP",
        "RED FLAGS AND SAFETY CONSIDERATIONS",
        "EVIDENCE GAPS",
        "SOURCES",
    ],
    "methodology": [
        "RESEARCH QUESTION FRAMEWORK",
        "MEASUREMENT TOOLS AND INSTRUMENTS",
        "STUDY DESIGN OPTIONS",
        "STATISTICAL METHODOLOGY",
        "EXISTING METHODOLOGICAL PRECEDENTS",
        "VALIDATION AND RELIABILITY DATA",
        "PRACTICAL CONSIDERATIONS",
        "EVIDENCE GAPS",
        "SOURCES",
    ],
}


def analyze_question(scenario: str) -> dict:
    """
    Use the big model to understand the scenario and produce all guidance needed
    for the pipeline.

    Returns:
        question_type       — what kind of report
        output_sections     — section headings for this specific question
        key_questions       — concrete questions the user wants answered
        audience            — who reads this and what they do with it
        report_instructions — synthesis guidance
        practitioner_title  — type of clinician managing this (e.g. surgeon, oncologist)
        bfs_guidance        — what research directions to explore
        dfs_guidance        — what to prioritise when extracting findings
        synthesis_guidance  — how to write the final report
    """
    log()
    log(bold("+" + "-" * 58 + "+"))
    log(bold("|  QUESTION ANALYSIS" + " " * 39 + "|"))
    log(bold("+" + "-" * 58 + "+"))

    prompt = (
        f"Clinical scenario:\n{scenario}\n\n"
        "Determine:\n"
        "1. What TYPE of question is this? Think about what the doctor will DO with the answer.\n"
        "   - 'pre_op': They have a specific patient and need a surgical/procedural brief\n"
        "   - 'research_design': They want to DESIGN a study or plan research\n"
        "   - 'literature_review': They want a comprehensive evidence summary on a topic\n"
        "   - 'clinical_comparison': They want to compare approaches/treatments/techniques\n"
        "   - 'case_discussion': They have a clinical case and need management guidance\n"
        "   - 'methodology': They need guidance on measurement/assessment methods\n\n"
        "2. What PRACTITIONER TYPE would manage this? (e.g. surgeon, oncologist, cardiologist, "
        "emergency physician, paediatrician, psychiatrist, radiologist, general clinician)\n\n"
        "3. What are the KEY QUESTIONS they want answered? Be specific. Extract 3-6.\n\n"
        "4. Who is the AUDIENCE and what will they do with this report?\n\n"
        "5. What REPORT SECTIONS should this brief have? Tailor to the question, not a rigid template.\n\n"
        "6. BFS GUIDANCE: What research directions should be explored? What aspects matter most?\n"
        "   Be specific about what evidence to look for, not generic keywords.\n\n"
        "7. DFS GUIDANCE: When extracting findings from search results, what should the researcher\n"
        "   prioritise? What data points, metrics, or outcomes are most important?\n\n"
        "8. SYNTHESIS GUIDANCE: How should the final report be written? What tone, depth, and\n"
        "   structure best serves this audience? What should be emphasised or avoided?\n\n"
        "Return JSON:\n"
        "{\n"
        '  "question_type": "pre_op|research_design|literature_review|clinical_comparison|case_discussion|methodology",\n'
        '  "practitioner_title": "the type of clinician who manages this (e.g. surgeon)",\n'
        '  "key_questions": ["specific question 1", ...],\n'
        '  "audience": "who reads this and what they do with it",\n'
        '  "report_instructions": "specific guidance for the report writer",\n'
        '  "suggested_sections": ["SECTION 1", "SECTION 2", ...],\n'
        '  "bfs_guidance": "what research directions to explore and why",\n'
        '  "dfs_guidance": "what to prioritise when extracting findings from search results",\n'
        '  "synthesis_guidance": "how to write the final report for this specific question and audience"\n'
        "}"
    )

    try:
        result = llm_json(
            [{"role": "user", "content": prompt}],
            system=QUESTION_ANALYSIS_SYSTEM,
            label="question analysis",
            phase="question_analysis",
        )

        qtype              = result.get("question_type", "literature_review")
        practitioner_title = result.get("practitioner_title", "clinician")
        key_qs             = result.get("key_questions", [])
        audience           = result.get("audience", "")
        instructions       = result.get("report_instructions", "")
        suggested          = result.get("suggested_sections", [])
        bfs_guidance       = result.get("bfs_guidance", "")
        dfs_guidance       = result.get("dfs_guidance", "")
        synthesis_guidance = result.get("synthesis_guidance", "")

        # Use LLM-suggested sections if provided, otherwise fall back to defaults
        if suggested and len(suggested) >= 3:
            output_sections = suggested
        else:
            output_sections = DEFAULT_SECTIONS.get(qtype, DEFAULT_SECTIONS["literature_review"])

        log(green(f"  Question type: {qtype}  |  Practitioner: {practitioner_title}"))
        log(dim(f"  Key questions: {len(key_qs)}"))
        for i, q in enumerate(key_qs[:4], 1):
            log(dim(f"    {i}. {q[:100]}"))
        if audience:
            log(dim(f"  Audience: {audience[:100]}"))

        return {
            "question_type":      qtype,
            "practitioner_title": practitioner_title,
            "output_sections":    output_sections,
            "key_questions":      key_qs,
            "audience":           audience,
            "report_instructions": instructions,
            "bfs_guidance":       bfs_guidance,
            "dfs_guidance":       dfs_guidance,
            "synthesis_guidance": synthesis_guidance,
        }

    except Exception as e:
        log(yellow(f"  Question analysis failed ({e}) — using generic defaults"))
        return {
            "question_type":      "unknown",
            "practitioner_title": "clinician",
            "output_sections":    [],
            "key_questions":      [],
            "audience":           "",
            "report_instructions": "",
            "bfs_guidance":       "",
            "dfs_guidance":       "",
            "synthesis_guidance": "",
        }

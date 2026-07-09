"""
config.py — All constants, environment variables, model configs, and system prompts.
Single source of truth. Import from here; never re-declare elsewhere.
"""

import os
import sys
from pathlib import Path

# ── [1.1] CRITICAL FIX: no hardcoded key default ──────────────────────────────
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
# Validated at startup in run.py — not here, so imports don't fail during testing

MODEL    = os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash")
BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

# ── Model tiers — big model for planning/synthesis, research model for execution ─
MODEL_TIER_BIG      = os.environ.get("MODEL_BIG",      "deepseek/deepseek-v4-pro")
MODEL_TIER_RESEARCH = os.environ.get("MODEL_RESEARCH", "deepseek/deepseek-v4-flash")

DATA_DIR = Path(os.environ.get("CRAM_DATA_DIR", Path.home() / ".cram"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── Research parameters ────────────────────────────────────────────────────────
BFS_BRANCHES       = int(os.environ.get("CRAM_BFS_BRANCHES", "6"))
DFS_DEPTH          = int(os.environ.get("CRAM_DFS_DEPTH", "2"))
RESULTS_PER_SOURCE = int(os.environ.get("CRAM_RESULTS_PER_SOURCE", "10"))
RATE_LIMIT_SLEEP   = float(os.environ.get("CRAM_RATE_LIMIT_SLEEP", "0.8"))
REQUEST_TIMEOUT    = int(os.environ.get("CRAM_REQUEST_TIMEOUT", "20"))
MAX_WORKERS        = int(os.environ.get("CRAM_MAX_WORKERS", "6"))
PARALLEL_BRANCHES  = int(os.environ.get("CRAM_PARALLEL_BRANCHES", str(BFS_BRANCHES)))  # all branches in parallel by default

# ── Input limits ──────────────────────────────────────────────────────────────
MEMORY_CHAR_LIMIT  = 2200
PROFILE_CHAR_LIMIT = 1375   # per-field practitioner profile (was SURGEON_CHAR_LIMIT)
MAX_SCENARIO_LEN   = 5000   # max chars for scenario input before truncation

# ── External API keys (optional features) ─────────────────────────────────────
CORE_API_KEY      = os.environ.get("CORE_API_KEY", "")
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "")
UNPAYWALL_EMAIL   = os.environ.get("UNPAYWALL_EMAIL", "cram@local.dev")
NCBI_API_KEY      = os.environ.get("NCBI_API_KEY", "")  # Free: ncbi.nlm.nih.gov/account/settings/
EXA_API_KEY       = os.environ.get("EXA_API_KEY", "")   # Exa agentic search (exa.ai)
BRAVE_API_KEY     = os.environ.get("BRAVE_API_KEY", "") # Brave Search API (api.search.brave.com)

# ── [14] Provider config — model per phase ─────────────────────────────────────
# Tier 1 (planning/synthesis) uses MODEL_BIG if set, else falls back to MODEL
# Tier 2 (research execution) uses MODEL_RESEARCH if set, else falls back to MODEL
_BIG = MODEL_TIER_BIG or MODEL
_RES = MODEL_TIER_RESEARCH or MODEL
PROVIDER_CONFIG = {
    # Tier 1 — Big model for planning + synthesis + safety
    "question_analysis": os.environ.get("MODEL_QUESTION_ANALYSIS", _BIG),
    "bfs":               os.environ.get("MODEL_BFS",               _BIG),
    "synthesis":         os.environ.get("MODEL_SYNTHESIS",         _BIG),
    "safety":            os.environ.get("MODEL_SAFETY",            _BIG),
    # Tier 2 — Research model for execution
    "verify":            os.environ.get("MODEL_VERIFY",            _RES),
    "compact":           os.environ.get("MODEL_COMPACT",           _RES),
    "dfs":               os.environ.get("MODEL_DFS",               _RES),
    "contradiction":     os.environ.get("MODEL_CONTRADICTION",     _RES),
    "alert":             os.environ.get("MODEL_ALERT",             _RES),
    "intake":            os.environ.get("MODEL_INTAKE",            _RES),
    "uu":                os.environ.get("MODEL_UU",                _RES),
    "intent":            os.environ.get("MODEL_INTENT",            _RES),
}
FALLBACK_MODEL = os.environ.get("OPENROUTER_FALLBACK_MODEL", "anthropic/claude-haiku-4-5")

# ── [18] Static system prompt components (cache-eligible) ─────────────────────
STATIC_SAFETY_RULES = (
    "CRITICAL RULES — NON-NEGOTIABLE:\n"
    "- Every clinical claim MUST cite a source (PMID, DOI, NCT ID, or URL).\n"
    "- If no source exists for a claim, state 'NO EVIDENCE FOUND'.\n"
    "- NEVER invent statistics, outcomes, or study results.\n"
    "- When uncertain, state the uncertainty explicitly.\n"
    "⚠️ = HIGH RISK | ✅ = strong evidence (RCT/large cohort) | "
    "⚡ = weak/limited evidence (case reports/preprints)\n"
    "Evidence grades: 🟢🟢 Cochrane/meta | 🟢 RCT | 🟡🟡 SR cohort | "
    "🟡 cohort | 🟠 case-control | 🔴 case series | ⚫ expert opinion | ⚠️ unverified\n"
)

# ── System prompts ─────────────────────────────────────────────────────────────

QUESTION_ANALYSIS_SYSTEM = (
    "You are a senior clinical researcher. A doctor has submitted a research question. "
    "Your job is to understand WHAT they actually want before any research begins.\n\n"
    "The question type determines the entire report structure:\n"
    "- pre_op: 'I have a patient with X, planning Y surgery' → surgical brief with pre-op/intraop/post-op\n"
    "- research_design: 'I want to study X' or 'prospective study on X' → methodology guide + prior art review\n"
    "- literature_review: 'What does the evidence say about X?' → systematic evidence summary\n"
    "- clinical_comparison: 'Compare A vs B for condition C' → structured comparison + evidence table\n"
    "- case_discussion: 'Patient presents with X, how to manage?' → diagnostic/management framework\n"
    "- methodology: 'How should we measure/assess X?' → measurement tools + study design guidance\n\n"
    "IMPORTANT:\n"
    "- Do NOT default to pre_op format. Most questions are NOT pre-op questions.\n"
    "- If the user has a typo (e.g., 'or' instead of '/'), interpret charitably. "
    "Do NOT flag common typos as errors.\n"
    "- Think about what the doctor will DO with this report.\n\n"
    "Return ONLY JSON. No prose. No markdown fences."
)

SYNTHESIS_SYSTEM = (
    "You are a senior clinical researcher writing a comprehensive evidence summary for a clinician. "
    "This report directly informs a high-stakes clinical decision. "
    "Be precise, cite sources with PMIDs/DOIs/NCT IDs, flag contradictions, highlight safety concerns.\n\n"
    "RETRACTION RULE: A source whose title or snippet is marked '⚠️ RETRACTED' or "
    "'⚠️ EXPRESSION OF CONCERN' must NOT be used to support any clinical recommendation. "
    "If such a source is relevant, mention it only to explicitly warn that it has been "
    "retracted / flagged and should not be relied upon.\n\n"
    "CRITICAL FORMATTING RULE: Any mermaid diagram MUST be wrapped in a markdown code fence. "
    "The fence MUST start with exactly three backticks followed immediately by the word mermaid "
    "(no space), like this: ```mermaid then the diagram content then closing ```. "
    "NEVER write 'mermaid' on a line by itself followed by diagram code — that is wrong. "
    "NEVER output raw mermaid syntax outside a code fence.\n\n"
    + STATIC_SAFETY_RULES
)

VERIFIER_SYSTEM = (
    "You are a clinical evidence verifier. You receive claimed research findings "
    "and the raw source snippets they were extracted from. "
    "Flag any finding that is overstated, unsupported, or potentially hallucinated. "
    "Be rigorous — a clinician will rely on this. Return ONLY JSON. No prose.\n\n"
    + STATIC_SAFETY_RULES
)

SAFETY_REVIEW_SYSTEM = (
    "You are a senior clinical safety reviewer. Review the compiled research report "
    "for a clinician about to perform or manage a procedure. Identify:\n"
    "1. Claims WITHOUT proper citations — flag UNSUPPORTED\n"
    "2. MISSING critical safety considerations\n"
    "3. CONTRADICTIONS between sources\n"
    "4. HALLUCINATED data (numbers not in sources)\n"
    "5. MISSING alternative approaches that are standard of care\n\n"
    + STATIC_SAFETY_RULES
    + "Return ONLY JSON. No prose."
)

BFS_SYSTEM = (
    "You are a senior clinical research strategist. Decompose the scenario into distinct "
    "research branches. ALL queries must be short PubMed keyword strings (4-8 words). "
    "NEVER write full sentences or questions as queries.\n"
    "✓ Good: 'rhinoplasty facial asymmetry long-term outcomes'\n"
    "✗ Bad:  'What are the outcomes of rhinoplasty in asymmetric faces?'\n"
    "Return ONLY valid JSON. No prose. No markdown fences."
)

DFS_SYSTEM = (
    "You are a clinical research analyst. Given search results: "
    "1) Extract clinically relevant findings with evidence grades. "
    "2) Generate 2 deeper follow-up PubMed keyword queries (4-8 words, no full sentences). "
    "3) Note gaps or contradictions in the evidence. "
    'Return ONLY JSON: {"key_findings":[...],"gaps":[...],"next_queries":["kw q1","kw q2"]}'
)

CONSOLIDATE_SYSTEM = (
    "You are a clinical evidence consolidator. Given raw search results and prior findings, "
    "produce a clean, deduplicated, structured evidence summary for this research branch. "
    "Preserve all specific clinical data, PMIDs, DOIs, sample sizes, complication rates. "
    "Resolve contradictions by noting both sides. "
    "Return structured Markdown. No JSON."
)

CONTRADICTION_SYSTEM = (
    "You are a clinical evidence analyst. Given consolidated findings from multiple research branches, "
    "identify contradictions, conflicts, and inconsistencies between branches. "
    "Return ONLY JSON: "
    '{"contradictions": [{"branches": [id1, id2], "topic": "...", '
    '"claim_a": "...", "claim_b": "...", "severity": "HIGH|MEDIUM|LOW", '
    '"recommendation": "how synthesiser should handle this"}]}'
)

COMPACTOR_SYSTEM = (
    "You are a clinical research distiller. Compress the provided evidence into a "
    "dense but complete summary, preserving all specific clinical findings, paper "
    "citations, PMIDs, DOIs, and safety flags. Remove duplication. "
    "Preserve ALL specific numbers, outcomes, and warnings. "
    "Return plain text, no JSON."
)

CHAT_SYSTEM = (
    "You are a clinical research assistant. The user has previously run an exhaustive "
    "medical literature search on a clinical scenario. You have been given the full "
    "consolidated evidence from that research session. "
    "Answer follow-up questions using ONLY this evidence — do not invent new facts. "
    "If a question cannot be answered from the evidence, say so explicitly and suggest "
    "which search branch might need to be re-run. "
    "Cite sources with PMIDs, DOIs, NCT IDs, or URLs from the evidence when possible. "
    "Flag ⚠️ for safety-critical information.\n\n"
    + STATIC_SAFETY_RULES
)

ALERT_CLASSIFIER_SYSTEM = (
    "You are a clinical safety classifier. You detect critical alerts in research findings. "
    "A critical alert is: a black-box warning, a Class I contraindication, a drug interaction "
    "with documented mortality signal, or a guideline that explicitly states "
    "'do not proceed if [condition]'. Be precise and conservative — only flag true alerts. "
    "Return ONLY JSON: {\"is_alert\": true/false, \"alert_text\": \"...\", \"source\": \"...\"}"
)

INTAKE_SYSTEM = (
    "You are a clinical intake processor. Parse a clinical scenario (structured or freeform) "
    "and extract a structured patient profile. Return ONLY JSON with these fields: "
    '{"procedure": "...", "age": 0, "sex": "...", "bmi": null, '
    '"comorbidities": [...], "medications": [...], "allergies": [...], '
    '"prior_surgeries": [...], "specific_concerns": [...], '
    '"time_pressure": "routine|urgent_24h|emergency", "field": "surgery|oncology|cardiology|..."}'
)

UNKNOWN_UNKNOWN_SYSTEM = (
    "You are an adversarial senior clinician. Your job is to find what a colleague's pre-op "
    "research missed. Be specific and actionable. Focus on:\n"
    "- Drug interactions not explicitly researched\n"
    "- Rare but documented complications for this exact combination of factors\n"
    "- Recent guideline changes (last 24 months) contradicting established practice\n"
    "- Population-specific data that may differ from trial populations\n"
    "- Things commonly missed in cases of this exact type\n"
    "Return ONLY JSON: "
    '{"uu_questions": [{"question": "Has anyone considered...", '
    '"priority": "HIGH|MEDIUM|LOW", "search_query": "4-8 word pubmed query"}]}'
)

# ── Injection security patterns ────────────────────────────────────────────────
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|earlier)",
    r"system\s*:",
    r"<\|im_start\|>",
    r"<\|endoftext\|>",
    r"role\s*:\s*(system|developer)",
    r"disregard\s+(all|any)\s+(instructions|rules)",
    r"you\s+are\s+now",
    r"new\s+(system|developer)\s+(prompt|instructions)",
]

# ── Generic medical search scope (used when no field-specific routing) ────────
GENERIC_DDG_SITES = (
    "site:nejm.org OR site:thelancet.com OR site:bmj.com OR site:jamanetwork.com "
    "OR site:ncbi.nlm.nih.gov OR site:who.int OR site:nice.org.uk OR site:uptodate.com "
    "OR site:medscape.com OR site:cochrane.org OR site:asco.org OR site:escardio.org "
    "OR site:idsociety.org OR site:aap.org OR site:acr.org OR site:icmr.gov.in "
    "OR site:aiims.edu OR site:cdc.gov OR site:emcrit.org OR site:acep.org"
)

# ── India-specific note (injected into synthesis context) ─────────────────────
INDIA_NOTE = (
    "Note where trial populations differ from Indian patient demographics "
    "(age of disease onset, BMI distributions, comorbidity patterns, genetic variants). "
    "Flag if Indian-population-specific data exists."
)

# ── Evidence grade symbols ─────────────────────────────────────────────────────
EVIDENCE_GRADES = {
    "1a": "🟢🟢",  # Cochrane SR / meta-analysis
    "1b": "🟢",    # RCT
    "2a": "🟡🟡",  # SR of cohort studies
    "2b": "🟡",    # Cohort / observational
    "3":  "🟠",    # Case-control
    "4":  "🔴",    # Case series / case report
    "5":  "⚫",    # Expert opinion / consensus
    "U":  "⚠️",   # Unverified
}

"""
pipeline/dfs.py — DFS per-branch research.
[9]  Parallel source fetches via ThreadPoolExecutor + serial write mutex
[10] BranchCheckpoint WAL for crash recovery
[16] Tree-based branch recovery on exception

Human-like research workflow per branch:
  1. Scan  — collect abstracts from all sources across all depths
  2. Triage — LLM screens abstracts; selects papers worth reading in full
  3. Read   — fetch full text (PMC/Unpaywall) for selected papers only
  4. Consolidate — synthesis sees: full papers (raw) + abstract survey (raw) + Tier-2/3 notes
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from cram.config import (
    DFS_DEPTH, DFS_SYSTEM, CONSOLIDATE_SYSTEM, RATE_LIMIT_SLEEP, MAX_WORKERS
)
from cram.provider.openrouter import llm, llm_json
from cram.memory.store import ResearchMemory, BranchCheckpoint
from cram.pipeline.verifier import verify_findings
from cram.pipeline.alerts import batch_classify_findings
from cram.pipeline.compactor import compact
from cram.log import log, bold, dim, green, yellow, red, blue, cyan, set_corr

# ── All search tools — imported here, not in each branch ──────────────────────
from cram.search.pubmed           import tool_pubmed
from cram.search.europe_pmc       import tool_europe_pmc
from cram.search.semantic_scholar import tool_semantic_scholar
from cram.search.clinical_trials  import tool_clinical_trials
from cram.search.cochrane         import tool_cochrane
from cram.search.crossref         import tool_crossref
from cram.search.medrxiv          import tool_medrxiv
from cram.search.brave            import tool_brave
from cram.search.youtube          import tool_youtube
from cram.search.guidelines       import tool_medical_guidelines
from cram.search.core_api         import tool_core
from cram.search.base             import dedup_results
from cram.search.unpaywall        import fetch_fulltext_for_results
from cram.search.ctri             import tool_ctri
from cram.search.openfda          import tool_openfda
from cram.search.exa              import tool_exa, exa_get_contents
from cram.search.retraction       import annotate_retractions

_TIER1 = frozenset({"PubMed", "Cochrane", "EuropePMC", "SemanticScholar", "ClinicalTrials"})
_TIER2 = frozenset({"CrossRef", "medRxiv", "CORE", "Guidelines", "OpenFDA"})

# Parallel search sources (name → tool). YouTube is added separately (needs extra args).
# Post-search enrichment (Unpaywall, PMC full-text) is not counted here.
_PARALLEL_SOURCES = [
    ("PubMed",          tool_pubmed),
    ("EuropePMC",       tool_europe_pmc),
    ("SemanticScholar", tool_semantic_scholar),
    ("ClinicalTrials",  tool_clinical_trials),
    ("Cochrane",        tool_cochrane),
    ("CrossRef",        tool_crossref),
    ("medRxiv",         tool_medrxiv),
    ("Brave",           tool_brave),
    ("Guidelines",      tool_medical_guidelines),
    ("CORE",            tool_core),
    ("CTRI",            tool_ctri),
    ("OpenFDA",         tool_openfda),
    ("Exa",             tool_exa),
]

# Total distinct sources queried per search (parallel pool + YouTube).
SOURCE_COUNT = len(_PARALLEL_SOURCES) + 1


# ── Source failure tracking ──────────────────────────────────────────────────
_source_failures: dict[str, int] = {}
_source_disabled: set[str] = set()
SOURCE_FAILURE_THRESHOLD = 3  # disable source after this many consecutive failures


def get_source_status() -> dict:
    """Return current source health status for reporting."""
    return {
        "failures": dict(_source_failures),
        "disabled": list(_source_disabled),
    }


def comprehensive_search(query: str, memory: Optional[ResearchMemory] = None,
                         clinical_question: str = "") -> list[dict]:
    """
    [9] Run all sources in parallel (ThreadPoolExecutor, MAX_WORKERS).
    Each source is already wrapped with @cached_search and with_retry.
    Sources that fail repeatedly are auto-disabled for the session.
    """
    log(cyan(f"  🔍  Comprehensive search: \"{query[:90]}\""))

    all_sources = _PARALLEL_SOURCES

    # Filter out disabled sources
    sources = [(name, fn) for name, fn in all_sources if name not in _source_disabled]
    if _source_disabled:
        log(dim(f"     (disabled sources: {', '.join(sorted(_source_disabled))})"))

    # YouTube gets special treatment — pass clinical_question for Gemini
    all_results: list[dict] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(fn, query): name for name, fn in sources}
        # YouTube — only if not disabled
        if "YouTube" not in _source_disabled:
            yt_future = ex.submit(tool_youtube, query, 10, clinical_question=clinical_question)
            futures[yt_future] = "YouTube"

        for future in as_completed(futures):
            name = futures[future]
            try:
                res = future.result()
                all_results.extend(res)
                # Reset failure count on success
                if name in _source_failures:
                    _source_failures[name] = 0
            except Exception as e:
                # Track failures
                _source_failures[name] = _source_failures.get(name, 0) + 1
                count = _source_failures[name]
                if count >= SOURCE_FAILURE_THRESHOLD:
                    _source_disabled.add(name)
                    log(yellow(f"     ⚠  {name} disabled after {count} failures: {e}"))
                else:
                    log(yellow(f"     ⚠  {name} failed ({count}/{SOURCE_FAILURE_THRESHOLD}): {e}"))

    all_results = dedup_results(all_results)

    # Flag retracted / expression-of-concern papers (PubMed pub-type = free;
    # non-PubMed DOIs checked against Crossref/Retraction Watch, bounded + cached)
    # before anything downstream cites them.
    annotate_retractions(all_results)

    if memory:
        memory.append_raw_results(all_results, query)

    source_counts: dict[str, int] = {}
    for r in all_results:
        src = r.get("source", "?")
        source_counts[src] = source_counts.get(src, 0) + 1

    active = len(sources) + (1 if "YouTube" not in _source_disabled else 0)
    total_possible = len(all_sources) + 1  # +1 for YouTube
    log(dim(f"     → {len(all_results)} total from {active}/{total_possible} sources "
            f"({', '.join(f'{k}:{v}' for k,v in source_counts.items())})"))

    return all_results


# ── Stage 2: Abstract triage ───────────────────────────────────────────────────

def _triage_abstracts(
    results: list[dict],
    angle: str,
    max_abstracts: int = 50,
) -> tuple[list[dict], list[dict]]:
    """
    Human-like abstract screening: decide which papers deserve full reading.

    Returns (full_read_list, abstract_only_list).
      full_read     — papers with specific clinical data; full text will be fetched
      abstract_only — relevant context; abstract is sufficient reference
      SKIP results are silently dropped

    Falls back to heuristic (top Tier-1 with PMIDs) if LLM fails.
    """
    # Only consider results with actual content
    candidates = [r for r in results if r.get("snippet") or r.get("title")]
    tier1 = [r for r in candidates if r.get("source") in _TIER1]
    tier23 = [r for r in candidates if r.get("source") not in _TIER1]
    ordered = (tier1 + tier23)[:max_abstracts]

    if not ordered:
        return [], []

    abstract_lines = []
    for i, r in enumerate(ordered):
        abstract_lines.append(
            f"[{i+1}] {r.get('source','')} PMID:{r.get('pmid','—')} "
            f"DOI:{(r.get('doi','') or '')[:30]}\n"
            f"Title: {r.get('title','')[:150]}\n"
            f"Abstract: {r.get('snippet','')[:350]}"
        )

    prompt = (
        f"Research question: {angle}\n\n"
        "Screen these abstracts for a clinical literature review. For each:\n"
        "- FULL: Read the full paper — abstract shows specific clinical data "
        "(exact doses, trial outcomes, guideline text, mortality figures)\n"
        "- ABSTRACT: Keep as reference — relevant context, abstract alone is enough\n"
        "- SKIP: Not relevant to this research question\n\n"
        "Be selective: typically 3-8 papers out of 50 warrant full reading.\n\n"
        "Abstracts:\n" + "\n\n".join(abstract_lines) + "\n\n"
        'JSON: {"decisions": [{"index": 1, "action": "FULL|ABSTRACT|SKIP", "reason": "brief"}]}'
    )

    try:
        result = llm_json(
            [{"role": "user", "content": prompt}],
            system=(
                "You are a senior medical librarian triaging abstracts for a clinical evidence review. "
                "FULL = paper contains specific quantitative clinical data directly relevant to the question. "
                "ABSTRACT = relevant context but no new specific data needed. "
                "SKIP = not relevant. Be selective about FULL — 3-8 per branch is typical."
            ),
            label="triage",
            phase="dfs",
        )
        decisions = result.get("decisions", [])

        full_read = [
            ordered[d["index"] - 1]
            for d in decisions
            if d.get("action") == "FULL"
            and 0 < d.get("index", 0) <= len(ordered)
            and (ordered[d["index"] - 1].get("pmid") or ordered[d["index"] - 1].get("doi"))
        ]
        abstract_only = [
            ordered[d["index"] - 1]
            for d in decisions
            if d.get("action") == "ABSTRACT"
            and 0 < d.get("index", 0) <= len(ordered)
        ]
        n_skip = sum(1 for d in decisions if d.get("action") == "SKIP")
        log(dim(f"  [TRIAGE] {len(full_read)} full read / {len(abstract_only)} abstract / {n_skip} skip "
                f"(from {len(ordered)} abstracts)"))

        # Safety: if LLM selected nothing for full read, take top 3 Tier-1 with PMIDs
        if not full_read:
            full_read = [r for r in tier1 if r.get("pmid") or r.get("doi")][:3]
            if full_read:
                log(dim(f"  [TRIAGE] fallback: selecting top {len(full_read)} Tier-1 papers for full read"))

        return full_read, abstract_only

    except Exception as e:
        log(yellow(f"  [TRIAGE] LLM failed ({e}), using heuristic"))
        full_read = [r for r in tier1 if r.get("pmid") or r.get("doi")][:5]
        full_read_ids = {id(r) for r in full_read}
        abstract_only = [r for r in ordered if id(r) not in full_read_ids]
        return full_read, abstract_only


# ── Stage 4: autoDream consolidation ──────────────────────────────────────────

def autodream_consolidate(branch: dict, raw_results: list[dict],
                           prior_findings: list[str],
                           memory: ResearchMemory,
                           fulltext_map: dict[str, str] | None = None,
                           question_analysis: dict | None = None,
                           full_read_results: list[dict] | None = None,
                           abstract_only_results: list[dict] | None = None) -> str:
    """
    Consolidate branch evidence with a three-tier structure:
      1. Papers read in full  — full text verbatim (no LLM compression)
      2. Abstract survey      — Tier-1 raw abstracts (no LLM compression)
      3. Tier-2/3 notes       — LLM synthesis of noisy/web sources only

    This mirrors how a human researcher consolidates: full papers carry all the
    detail; abstracts provide broader context; web/guidelines get summarised.
    """
    bid   = branch.get("branch_id", "?")
    angle = branch.get("angle", "")
    set_corr(branch_id=str(bid))

    log(blue(f"  [DREAM] autoDream consolidation branch [{bid}]: {angle}"))

    index_snapshot = memory.read_index()
    log(dim(f"  [DREAM] Phase 1/4 Orient — {index_snapshot.count('✅')} branches indexed"))

    n_full     = len(full_read_results or [])
    n_abstract = len(abstract_only_results or [])
    n_total    = len(raw_results)
    log(dim(f"  [DREAM] Phase 3/4 Consolidate — {n_total} results: "
            f"{n_full} full papers + {n_abstract} abstract survey + Tier-2/3 synthesis"))

    parts: list[str] = []

    # ── Section 1: Papers read in full (no LLM compression) ──────────────────
    full_paper_parts: list[str] = []

    # PMC / Unpaywall full texts — look up by pmid or doi key
    for r in (full_read_results or []):
        key = r.get("pmid") or r.get("doi") or ""
        text = (fulltext_map or {}).get(key, "")
        if text:
            full_paper_parts.append(
                f"**{r.get('title', 'Untitled')}**\n"
                f"Source: {r.get('source','')} | PMID: {r.get('pmid','')} | "
                f"DOI: {r.get('doi','')}\n\n"
                f"{text}"
            )

    # Exa / web full texts — URL-keyed entries in fulltext_map
    for key, text in (fulltext_map or {}).items():
        if key.startswith("http") and text.strip():
            exa_r = next((r for r in raw_results if r.get("url") == key), {})
            full_paper_parts.append(
                f"**{exa_r.get('title', key[:80])}**\n"
                f"Source: {exa_r.get('source', 'Web')} | URL: {key[:100]}\n\n"
                f"{text}"
            )

    if full_paper_parts:
        parts.append(
            f"## Papers Read in Full ({len(full_paper_parts)} papers)\n\n"
            + "\n\n---\n\n".join(full_paper_parts)
        )

    # ── Section 2: Abstract survey — Tier-1 only, verbatim (no compression) ──
    # Includes both abstract_only Tier-1 results AND any full_read papers
    # whose full text was not available (so abstract is best we have)
    fetched_keys = set((fulltext_map or {}).keys())
    full_read_ids = {id(r) for r in (full_read_results or [])}
    unfetched_full = [
        r for r in (full_read_results or [])
        if not ((r.get("pmid") or r.get("doi") or "") in fetched_keys)
    ]
    t1_abstract = [r for r in (abstract_only_results or []) if r.get("source") in _TIER1]
    abstract_survey = unfetched_full + t1_abstract

    if abstract_survey:
        survey_lines = [
            f"[{r.get('source','')}] PMID:{r.get('pmid','')} DOI:{(r.get('doi','') or '')[:40]}\n"
            f"**{r.get('title','')}**\n"
            f"{r.get('snippet','')}"
            for r in abstract_survey[:30]
        ]
        parts.append(
            f"## Abstract Survey — Tier-1 Academic Sources ({len(abstract_survey[:30])} abstracts)\n"
            "*Not read in full — kept as reference. Cite PMIDs if relevant.*\n\n"
            + "\n\n".join(survey_lines)
        )

    # ── Section 3: Tier-2/3 notes — LLM synthesis of noisy sources ───────────
    tier23_pool = [r for r in raw_results if r.get("source") not in _TIER1]
    tier23_selected = tier23_pool[:15]
    tier23_snippets = "\n\n".join(
        f"[{r['source']}] {r.get('pmid', r.get('doi', r.get('nct_id', 'n/a')))} "
        f"{r.get('title','')}\n{r.get('snippet','')}"
        for r in tier23_selected
    )

    tier23_notes = ""
    if tier23_snippets.strip():
        dfs_guidance = (question_analysis or {}).get("dfs_guidance", "")
        focus_line = f"DFS focus: {dfs_guidance}" if dfs_guidance else "Clinical Research"
        consolidate_prompt = (
            f"Research branch: {angle}\n"
            f"{focus_line}\n\n"
            f"Prior findings:\n" + "\n".join(f"- {f}" for f in prior_findings[:8]) +
            f"\n\nTier-2/3 source results (guidelines, preprints, web, drug databases):\n"
            f"{tier23_snippets[:5000]}\n\n"
            "Produce a concise evidence note for these non-academic sources. Include:\n"
            "- Guideline recommendations (with source/year)\n"
            "- Relevant clinical trials (NCT IDs)\n"
            "- Drug safety / interaction findings\n"
            "- Evidence gaps not covered by academic sources\n\n"
            "Use **Finding N:** headers. Cite every claim."
        )
        try:
            tier23_notes = llm(
                [{"role": "user", "content": consolidate_prompt}],
                system=CONSOLIDATE_SYSTEM,
                temperature=0.1,
                label=f"b{bid} consolidate",
                phase="dfs",
            )
        except Exception as e:
            log(yellow(f"  [DREAM] Tier-2/3 consolidation failed ({e}), using raw snippets"))
            tier23_notes = tier23_snippets[:3000]

        if tier23_notes.strip():
            parts.append(f"## Tier-2/3 Source Notes\n{tier23_notes}")

    # Fallback: if all sections empty, dump raw abstracts
    if not parts:
        parts.append("\n\n".join(
            f"[{r['source']}] {r.get('title','')}\n{r.get('snippet','')}"
            for r in raw_results[:20]
        ))

    consolidated = "\n\n".join(parts)

    # Phase 4 — Write (strict discipline: file first, index on success)
    log(dim("  [DREAM] Phase 4/4 Write — file → index"))
    evidence_content = (
        f"# Branch {bid}: {angle}\n"
        f"**Rationale:** {branch.get('rationale','')}\n\n"
        f"{consolidated}\n\n"
        f"---\n"
        f"*Sources: {n_total} collected | {n_full} read in full | "
        f"{n_abstract} abstract survey | {len(tier23_selected)} Tier-2/3*\n"
    )
    written = memory.write_branch_evidence(bid, angle, evidence_content)
    if written:
        log(blue(f"  [DREAM] ✅ Branch [{bid}] consolidated and indexed"))
    else:
        log(red(f"  [DREAM] ❌ Write failed for branch [{bid}]"))

    return consolidated


# ── Inner DFS loop ─────────────────────────────────────────────────────────────

def _dfs_branch_inner(branch: dict, scenario: str, memory: ResearchMemory,
                      patient_profile: str = "",
                      depth: int = DFS_DEPTH,
                      question_analysis: dict | None = None) -> dict:
    bid   = branch.get("branch_id", "?")
    angle = branch.get("angle", "")

    all_raw_results: list[dict] = []
    all_findings:    list[str]  = []
    exa_fulltext:    dict[str, str] = {}  # URL-keyed; fetched immediately (no PMIDs)

    # ── Stage 1: Search ────────────────────────────────────────────────────────

    # Depth 0 — primary query
    log(bold(f"  [Depth 0] Primary search"))
    set_corr(branch_id=str(bid), depth="0")
    r0 = comprehensive_search(
        branch["primary_query"], memory=memory,
        clinical_question=angle,
    )
    all_raw_results.extend(r0)

    # Exa web contents — fetch immediately (URL-based, no PMID/DOI available)
    exa_results = sorted(
        [r for r in r0 if r.get("source") == "Exa" and r.get("url") and r.get("score", 0) > 0],
        key=lambda r: r.get("score", 0), reverse=True,
    )
    if exa_results:
        exa_urls = [r["url"] for r in exa_results[:5]]
        exa_texts = exa_get_contents(exa_urls, max_chars=8000)
        if exa_texts:
            exa_fulltext.update(exa_texts)
            log(dim(f"     🔎 Exa full text retrieved for {len(exa_texts)} result(s)"))

    current_queries = branch.get("followup_queries", [])[:2]

    for d in range(1, depth + 1):
        if not current_queries:
            break
        log(bold(f"  [Depth {d}] Follow-up ({len(current_queries)} queries)"))
        set_corr(branch_id=str(bid), depth=str(d))

        level_results: list[dict] = []
        for q in current_queries[:2]:
            res = comprehensive_search(q, memory=memory,
                                       clinical_question=angle)
            level_results.extend(res)
            all_raw_results.extend(res)

        # Synthesis snippets: current depth only (focused signal)
        snippets = "\n\n".join(
            f"[{r['source']}] {r.get('title','')}\n{r.get('snippet','')}"
            for r in level_results[:15]
        )

        # Verifier snippets: current depth results FIRST (findings were extracted from
        # these), then supplement with earlier results. Avoids the off-by-depth bug where
        # depth-2 findings get verified against depth-0 snippets only.
        level_ids = {id(r) for r in level_results}
        other_results = [r for r in all_raw_results if id(r) not in level_ids]
        verify_pool = list(level_results) + other_results
        verify_snippets = "\n\n".join(
            f"[{r['source']}] {r.get('title','')}\n{r.get('snippet','')}"
            for r in verify_pool[:80]
        )

        log(dim(f"  [Depth {d}] LLM synthesis ({len(level_results)} results)..."))

        dfs_guidance = (question_analysis or {}).get("dfs_guidance", "")
        focus_line = f"Focus: {dfs_guidance}" if dfs_guidance else "Clinical Research"
        synth_prompt = (
            f"Scenario: {scenario}\n"
            f"Branch: {angle}\n"
            f"{focus_line}\n\n"
            f"Results at depth {d}:\n{snippets}\n\n"
            "Extract ONLY findings explicitly stated in the results above — do NOT add facts "
            "from your training knowledge. If a fact is not in the snippets, do not include it. "
            "Include: source PMID/DOI, evidence grade, and 2 deeper PubMed keyword queries (4-8 words).\n"
            'JSON: {"key_findings":["finding with PMID/source [grade]",...],"gaps":[...],'
            '"next_queries":["kw q1","kw q2"]}'
        )

        try:
            synth = llm_json(
                [{"role": "user", "content": synth_prompt}],
                system=DFS_SYSTEM,
                label=f"b{bid} d{d}",
                phase="dfs",
            )
        except Exception as e:
            log(yellow(f"  ⚠  Synthesis error at depth {d}: {e}"))
            synth = {"key_findings": [], "gaps": [], "next_queries": []}

        # Guard against a JSON array response (llm_json can return a list)
        if not isinstance(synth, dict):
            synth = {"key_findings": [], "gaps": [], "next_queries": []}

        raw_findings = synth.get("key_findings", [])

        # [11] Verify findings against accumulated evidence
        verified = verify_findings(
            raw_findings, verify_snippets,
            label=f"b{bid} d{d}", memory=memory,
        )

        # [7 new] Alert classification — real-time, before continuing
        batch_classify_findings(verified, patient_profile, memory, context=snippets)

        all_findings.extend(verified)

        for f in verified[:4]:
            log(dim(f"    • {f[:115]}"))
        for g in synth.get("gaps", [])[:2]:
            log(dim(f"    ⚡ gap: {g[:100]}"))

        current_queries = synth.get("next_queries", [])

    # ── Fallback: re-search with broadened query if branch found nothing ───────
    if not all_findings:
        log(yellow(f"  [B{bid}] 0 verified findings — retrying with broadened query"))
        try:
            broaden_prompt = (
                f"Branch topic: {angle}\n"
                f"Original query: {branch['primary_query']}\n\n"
                "This search returned no verifiable findings. Generate ONE broader PubMed "
                "query (4-8 words) that approaches the same clinical question from a "
                "higher level (e.g. use class names instead of specific drugs, use broader "
                "MeSH terms). Return ONLY the query string, nothing else."
            )
            broad_query = llm(
                [{"role": "user", "content": broaden_prompt}],
                label=f"b{bid} broaden",
                phase="dfs",
            ).strip().strip('"').strip("'")

            if broad_query and len(broad_query) > 5:
                log(dim(f"  [B{bid}] Broadened query: \"{broad_query}\""))
                broad_results = comprehensive_search(
                    broad_query, memory=memory, clinical_question=angle,
                )
                all_raw_results.extend(broad_results)

                if broad_results:
                    broad_snippets = "\n\n".join(
                        f"[{r['source']}] {r.get('title','')}\n{r.get('snippet','')}"
                        for r in broad_results[:8]
                    )
                    dfs_guidance = (question_analysis or {}).get("dfs_guidance", "")
                    focus_line = f"Focus: {dfs_guidance}" if dfs_guidance else "Clinical Research"
                    broad_synth = llm_json(
                        [{"role": "user", "content": (
                            f"Scenario: {scenario}\nBranch: {angle}\n{focus_line}\n\n"
                            f"Broadened search results:\n{broad_snippets}\n\n"
                            "Extract any verifiable findings. Be less strict — include "
                            "guideline recommendations and consensus statements even if "
                            "specific trial data is absent.\n"
                            'JSON: {"key_findings":["finding [grade]",...],"gaps":[...],'
                            '"next_queries":[]}'
                        )}],
                        system=DFS_SYSTEM,
                        label=f"b{bid} broad-synth",
                        phase="dfs",
                    )
                    broad_verified = verify_findings(
                        broad_synth.get("key_findings", []),
                        broad_snippets,
                        label=f"b{bid} broad-verify",
                        memory=memory,
                    )
                    if broad_verified:
                        batch_classify_findings(broad_verified, patient_profile, memory,
                                                context=broad_snippets)
                        all_findings.extend(broad_verified)
                        log(green(f"  [B{bid}] Broadened search recovered {len(broad_verified)} finding(s)"))
        except Exception as e:
            log(yellow(f"  [B{bid}] Broadened search failed ({e})"))

    # ── Stage 2: Abstract triage ───────────────────────────────────────────────
    log(dim(f"  [TRIAGE] Screening {len(all_raw_results)} abstracts for branch [{bid}]..."))
    full_read_results, abstract_only_results = _triage_abstracts(all_raw_results, angle)

    # ── Stage 3: Fetch full text for selected papers ───────────────────────────
    # Start with Exa web contents (already fetched), then add PMC/Unpaywall
    fulltext_map: dict[str, str] = dict(exa_fulltext)

    if full_read_results:
        pmcid_texts = fetch_fulltext_for_results(
            full_read_results,
            max_papers=len(full_read_results),  # fetch ALL selected papers
            query=angle,
        )
        fulltext_map.update(pmcid_texts)
        log(dim(f"     🔓 Full text: {len(pmcid_texts)}/{len(full_read_results)} papers "
                f"retrieved (PMC/Unpaywall)"))

    # ── Stage 4: Consolidate ───────────────────────────────────────────────────
    consolidated = autodream_consolidate(
        branch, all_raw_results, all_findings, memory,
        fulltext_map=fulltext_map,
        question_analysis=question_analysis,
        full_read_results=full_read_results,
        abstract_only_results=abstract_only_results,
    )

    log(green(f"\n  ✅ Branch [{bid}] — {len(all_raw_results)} raw, {len(all_findings)} verified, "
              f"{len(full_read_results)} full papers read"))

    return {
        "branch_id":   bid,
        "angle":       angle,
        "rationale":   branch.get("rationale", ""),
        "raw_results": all_raw_results,
        "findings":    all_findings,
        "consolidated":consolidated,
    }


# ── Outer DFS with [16] tree-based recovery ────────────────────────────────────

def dfs_branch(branch: dict, scenario: str, memory: ResearchMemory,
               patient_profile: str = "",
               depth: int = DFS_DEPTH,
               checkpoint: Optional[BranchCheckpoint] = None,
               question_analysis: dict | None = None) -> dict:
    """
    [16] If DFS raises, retry with primary query only (narrowed scope).
    Partial evidence written so synthesis still gets something.
    """
    bid   = branch.get("branch_id", "?")
    angle = branch.get("angle", "")
    set_corr(branch_id=str(bid), depth="0")

    log()
    log(bold("─" * 60))
    log(bold(f"  🔬  DFS [{bid}]: {angle}"))
    log(bold("─" * 60))

    try:
        result = _dfs_branch_inner(
            branch, scenario, memory, patient_profile, depth,
            question_analysis=question_analysis,
        )
        if checkpoint:
            checkpoint.mark_complete(bid)
        return result

    except Exception as e:
        log(red(f"  [DFS] Branch [{bid}] failed: {e}"))
        log(yellow(f"  [DFS] Tree recovery: retrying branch [{bid}] with narrowed scope..."))
        if checkpoint:
            checkpoint.mark_partial(bid)

        try:
            recovery_results = comprehensive_search(
                branch.get("primary_query", angle),
                memory=memory,
            )
            snippets = "\n\n".join(
                f"[{r['source']}] {r.get('title','')}\n{r.get('snippet','')}"
                for r in recovery_results[:8]
            )
            recovery_finding = llm(
                [{"role": "user", "content":
                  f"Scenario: {scenario}\nBranch: {angle}\n\n"
                  f"Recovery results:\n{snippets[:2500]}\n\n"
                  "Extract the 3-5 most important clinical findings as bullet points. "
                  "Cite sources. Mark evidence quality."}],
                system=DFS_SYSTEM,
                label=f"b{bid} recovery",
                phase="dfs",
            )

            partial_content = (
                f"# Branch {bid}: {angle} [PARTIAL — recovery mode]\n"
                f"⚡ Full DFS failed. Recovery mode used (primary query only).\n\n"
                f"{recovery_finding}\n\n"
                f"---\n*Sources: {len(recovery_results)} (recovery only)*\n"
            )
            memory.write_branch_evidence(bid, angle + " [partial]", partial_content)
            if checkpoint:
                checkpoint.mark_complete(bid)

            return {
                "branch_id":   bid,
                "angle":       angle + " [partial]",
                "rationale":   branch.get("rationale", ""),
                "raw_results": recovery_results,
                "findings":    [recovery_finding],
                "consolidated":recovery_finding,
            }

        except Exception as e2:
            log(red(f"  [DFS] Recovery also failed for [{bid}]: {e2}"))
            if checkpoint:
                checkpoint.mark_partial(bid)
            return {
                "branch_id":   bid,
                "angle":       angle + " [failed]",
                "rationale":   branch.get("rationale", ""),
                "raw_results": [],
                "findings":    [],
                "consolidated":"",
            }

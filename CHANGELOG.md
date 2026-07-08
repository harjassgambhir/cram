# CRAM-1 — Changelog

## v8 — Upcoming

### Planned

- **Citation verification stage** — post-synthesis check of each (claim, PMID/DOI) pair against the actual paper's full text. A hallucinated citation should be impossible to publish.
- **Verifier as confidence score** — replace binary KEEP/REMOVE with a 0–1 confidence score. Borderline findings currently discarded will instead surface with `[LOW CONFIDENCE]` so the doctor can decide, not the agent.
- **Structured JSON synthesis** — synthesis output as a typed schema before rendering to markdown. Eliminates run-to-run formatting drift.
- **India formulary integration** — local lookup of Indian brand names, generic equivalents, essential-list tier, and common substitutions. Prevents recommendations that are correct globally but unavailable in India.
- **Temperature audit** — every LLM call audited for appropriate temperature. Synthesis and citation-sensitive calls should be at or near 0.
- **PRISMA-style per-query logging** — machine-readable record of what was searched, what was found, what was discarded at each stage. Required for clinical audit trails.

---

## v7 — 2026-04 to 2026-05

The rewrite. `mini-claude.py` became a proper Python package. Every substantive design decision from v6 was revisited.

### Round 3 — Architecture Overhaul (2026-04-13)

**Dynamic question understanding (`question_analyzer.py`)**  
Replaced hardcoded field profiles with a live LLM pass at the start of every run. The model reads the raw scenario and produces: question type, key questions, output sections appropriate for that question, synthesis guidance, and practitioner framing. A TB study design question no longer receives a surgical operating room checklist. The whole report structure is generated fresh from the question.

Six question types emerged: `pre_op`, `research_design`, `literature_review`, `clinical_comparison`, `case_discussion`, `methodology`. These are labels, not templates — the output sections are generated, not looked up.

**Three-tier model architecture**  
`MODEL_BIG` for reasoning-heavy phases (question analysis, BFS, synthesis). `MODEL_RESEARCH` for execution-heavy phases (DFS, verification, alert classification, compaction). Default: DeepSeek V4 Pro + Flash. Cost for a full 6-branch run: ~$0.10–0.20.

**Intent-aware BFS**  
Question analysis output passed into BFS prompt so research branches actually match what was asked, not a generic decomposition.

**Plan phase editing**  
During the plan phase, the user can now `add <topic>`, `edit N <desc>`, or `skip N` before DFS begins. Addresses the "I want to add a research direction the agent didn't think of" workflow.

**Exa agentic search**  
DuckDuckGo replaced with Exa for web search. Exa's neural+keyword hybrid returns full-page text for top results, not just snippets. Immediate quality improvement on guideline content.

**PubMed efetch full abstracts**  
Changed from esummary (truncated at 250 chars) to esearch → esummary → efetch pipeline, returning complete abstracts. Evidence grading from PublicationType (🟢🟢 for meta-analysis, 🟢 for RCT, etc.) added at this stage.

**Brave Search replaces DDG**  
Dual-pass: first unscoped for broad coverage, then scoped to trusted medical domains. API key required; free tier is generous.

**Critical alerts — real-time**  
Black-box warnings, Class I contraindications, drug interactions with mortality signals now surface as interrupts during DFS — written to `ALERTS.md` immediately, not discovered at synthesis.

**dotenv loading order fix**  
Critical bug: `config.py` was imported before `.env` was loaded, so `MODEL_BIG` was silently ignored even when set. Fixed by moving `load_dotenv()` to the top of `cli.py` before any cram imports.

---

### Round 4 — Search Quality (2026-04-13)

**Exa full-page contents wired into DFS**  
After each depth-0 search, Exa's `get_contents` API fetches full text for top results. Merged into `fulltext_map` used by the verifier. First step toward full-text verification.

**Semantic verifier rescue (Layer 3)**  
A finding about to be discarded by the verifier gets a second chance. Layer 3 searches all accumulated raw results for any snippet that semantically supports the claim. Replaced the prior word-overlap heuristic with an LLM semantic check.

**Chat slash autocomplete**  
Post-research Q&A now has Tab completion for slash commands using `prompt_toolkit`. `/grep`, `/search`, `/branches`, `/report` commands added.

**Cost and token tracking**  
Per-model pricing table in `provider/openrouter.py`. Every session ends with an estimated cost breakdown per phase. Running blind on cost is over.

**Mid-research branch injection**  
Non-blocking stdin thread during DFS. Type a question mid-run and it is queued as a new branch, inserted after the current one completes. The model evaluates it in the context of what has already been researched.

**MeSH expansion for PubMed**  
If a PubMed query returns fewer than half the expected results, the querytranslation is extracted from esearch and used to run a supplemental MeSH-expanded search.

---

### Round 5 — Correctness and Reliability (2026-05)

**Profiles removed entirely**  
After Round 3 decoupled profiles from synthesis, it became clear the profiles were residual structure with no remaining function. Eight specialty dataclasses removed. `profiles/base.py` and `profiles/registry.py` kept as empty stubs for import compatibility. Research guidance is now 100% dynamic.

**Parallel branch execution**  
All 6 DFS branches now run simultaneously using `ThreadPoolExecutor`. The prior sequential-with-parallelism-inside-each-branch pattern is replaced with true branch-level parallelism. Wall-clock time for a 6-branch depth-2 run: ~10–15 min.

**Pipeline checkpointing and resume**  
`PipelineCheckpoint` saves state after DFS, after unknown-unknowns, and after contradiction detection. If a run fails on a 402 credit exhaustion error, the exact `cram --resume-session PATH` command is printed. Resuming a post-DFS failure no longer re-runs 60+ LLM calls.

**Compaction-safety cascade fix**  
The compactor was compressing evidence that contained safety flags, losing the flags in the output. Fixed by passing safety flags through as a protected set before compaction.

**Per-finding alert → batch per depth level**  
Alert classification now runs once per depth level (one LLM call) instead of once per finding. Reduces alert overhead from ~10 calls per branch to 2.

**Combined review (self-review + safety review merged)**  
Two sequential post-synthesis passes on the full 20k-char report replaced with one call returning `{"report": "...", "safety_issues": [...]}`. Sanity check: if output < 70% of input length, the LLM rewrote the report; discard and keep original. One fewer big-model call on the most expensive prompt in the pipeline.

**OpenAlex, DOAJ, DrugSafety removed**  
OpenAlex and Semantic Scholar had ~70% overlap. DOAJ was a subset of PubMed + CORE. The DDG-based drug safety tool was slower and less reliable than OpenFDA. Down to 13 active sources with no clinical coverage loss.

**Rich TUI**  
Plain `print()` with manual ANSI codes replaced with Rich. Section rules, error panels, animated spinners during LLM calls, stats table at session end.

---

### Round 6 — Information Retention (2026-05, this release)

**Human-like research workflow in DFS**  
The autoDream LLM consolidation was compressing full Tier-1 papers (PubMed, Cochrane, etc.) into summaries — a summary-of-summary that lost dosing numbers, p-values, and patient counts before the verifier ever saw them.

New 4-stage workflow matching how a doctor does a literature review:
1. **Scan** — collect all results across all depth levels
2. **Triage** — LLM screens up to 50 abstracts, classifies each as FULL/ABSTRACT/SKIP
3. **Read** — PMC full text fetched for FULL-classified papers (up to 15,000 chars each, keyword-scored chunk selection)
4. **Consolidate** — Tier-1 sources stored verbatim (no LLM compression); only Tier-2/3 go through LLM synthesis

Result: full dosing numbers, p-values, and safety signals survive to the verifier unchanged.

**Verifier depth-pool bug fixed**  
At depth 2, the verifier was receiving only `all_raw_results[:50]` — which at that point only contained depth-0 results. Depth-2 findings were being verified against the wrong papers and discarded at ~100%. Fix: current depth's results go first in the verify pool, earlier depth results supplementary.

**Citation grounding in synthesis**  
Bare inline DOIs (`(10.3390/jcm806)`) were not matched by the prior citation-stripping regex. Fixed. Citation pool hint expanded from 60 IDs to the full pool organized by type. Synthesis temperature lowered 0.2 → 0.1.

**PMC full-text chunking fixed**  
PMC plain text has no empty lines between paragraphs, so the prior `\n{2,}` split produced one giant block and selected nothing. Replaced with 600-char chunk windows scored by clinical keyword density (results, dosing, outcomes, hazard ratio, etc.). High-scoring chunks prioritized.

---

### Round 7 — UX and Robustness (2026-05-28)

**Safety review correction pass**  
The safety review no longer just flags problems — it fixes them. When the combined review finds issues (`ready_for_clinical_use: false`), a correction pass runs at temperature 0.0 to rewrite the specific sections with problems. A second review confirms the fixes held. If residual issues remain after correction they are still surfaced in the safety section so the clinician sees them; the NOT READY banner only appears when the LLM couldn't fix them. Duplicate safety section headers and over-broad rewrites are guarded against.

**Safety review retry on long reports**  
The combined review LLM call was failing with "Response ended prematurely" on reports longer than ~20k chars. Fixed: first attempt uses the full report text (capped at 16k chars); on failure, retries with 10k chars. Result processing is now correctly outside the retry loop.

**JSON parse robustness**  
`llm_json()` was crashing on "Extra data" errors — valid JSON followed by trailing explanation text (a common LLM behaviour). Fixed with a two-stage fallback: (1) slice at `exc.pos` to extract just the first valid JSON object; (2) walk character by character with `raw_decode` to find the first parseable `{` or `[`. Fixes `[INTAKE] Interrogation failed` on scenarios where the model appended commentary after the JSON.

**REPL auto-enters chat after research**  
In interactive mode, after a research run completes the REPL now automatically drops into the chat session — same behaviour as `cram -s "..."`. No need to type `/chat` manually. Type `/quit` inside chat to return to the `cram>` prompt. ANSI terminal state is reset before the chat prompt renders, fixing invisible input cursor after the coloured research output.

**`/pdf` toggle in interactive mode**  
PDF export was only available via `--pdf` on the command line; interactive mode had no equivalent. Added `/pdf` toggle command. The prompt shows `cram [pdf]>` when PDF export is active so the user always knows the current state. Toggling `/pdf` before typing a scenario enables PDF for that run and all subsequent runs in the session.

**`/help` updated**  
REPL `/help` now lists `/pdf`, clarifies that `/chat [N]` is for loading past sessions (chat auto-enters after research), and shows the available chat commands inline so users don't need to enter chat to discover them.

---

## v6 — 2026-03 (pre-restructure)

`medical-research-agent-v6.py` — monolithic single-file script. BFS/DFS pipeline established here. The architecture that became v7 was already recognisable: parallel branch execution, per-finding verification, synthesis prompt, chat loop.

Known issues going into v7:
- Hardcoded API key in source (`OPENROUTER_API_KEY = os.environ.get(..., "sk-or-v1-ca27d...")`)
- SQLite cache without WAL mode — `database is locked` errors under parallel workers
- Cochrane tool appended a fake "placeholder" result on scrape failure, which was ingested as evidence
- All output in surgical brief format regardless of question type
- No structured intake — raw freeform scenario only

---

## v1–v5 — 2025–2026

The research tool started as a single Python script called `mini-claude.py`. Early versions were single-threaded, searched 3–4 sources (PubMed + a few others), and produced unstructured output. Each major version added parallelism, sources, and verification logic.

Key milestones:
- **v1** — PubMed + DDG + DuckDuckGo, sequential search, raw LLM output
- **v2** — Parallel source fetching with `ThreadPoolExecutor`
- **v3** — SQLite query cache, deduplication, first verifier pass
- **v4** — BFS decomposition into research branches (the structural shift that made everything else possible)
- **v5** — Per-branch DFS with depth control, contradiction detection, unknown-unknowns pass
- **v6** — Profiles system, 16 sources, synthesis prompt overhaul, chat loop

The BFS → DFS architecture in v4 is the core insight that never changed: decompose the question into parallel threads, search deeply per thread, then synthesise across threads. Everything since v4 is improving the quality of each step.

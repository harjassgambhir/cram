# CRAM-1
## Deep clinical evidence synthesis in minutes, not hours

[![CI](https://github.com/harjassgambhir/cram/actions/workflows/ci.yml/badge.svg)](https://github.com/harjassgambhir/cram/actions/workflows/ci.yml)

AI-assisted clinical literature synthesis for doctors. Takes any clinical question — pre-op planning, study design, literature review, drug comparison — searches 13 medical sources in parallel, verifies every finding against raw source text, and produces a structured, evidence-graded report that actually answers what was asked. A full run takes ~10–15 minutes: this is a deep lit-review tool, not a bedside lookup.

> ⚠️ For clinical reference only. Does not replace clinical judgment, institutional protocols, or specialist consultation. Every claim must be verified against the cited source documents.

---

## Quick Start

```bash
# 1. Clone and install (requires Python 3.11+, uv recommended)
git clone https://github.com/harjassgambhir/cram.git
cd cram

# With uv (recommended):
source .venv/bin/activate
uv sync

# Or with pip:
pip install -e .

# 2. Configure
cp .env.example .env
# Edit .env — set OPENROUTER_API_KEY at minimum

# 3. Run
uv run cram                                    # interactive REPL
uv run cram -s "58F HER2+ breast cancer, planned trastuzumab + pertuzumab — cardiac monitoring?"
uv run cram -s "..." --auto --no-chat          # non-interactive, no chat after
uv run cram -s "..." --pdf                     # also export PDF
```

---

## What It Does

CRAM-1 runs a structured research pipeline for every query:

```
Your question
    ↓
Question analysis      — detects question type, generates output structure
    ↓
BFS decomposition      — splits into 6 parallel research branches
    ↓
DFS search (parallel)  — searches 13 sources per branch, 2 depth levels
    ↓
Verification           — every finding checked against raw source text
    ↓
Alert classification   — real-time detection of contraindications / black-box warnings
    ↓
Unknown unknowns       — adversarial pass to find what was missed
    ↓
Contradiction check    — flags inter-branch conflicts
    ↓
Synthesis              — structured evidence-graded clinical brief
    ↓
Combined review        — inline quality markers + safety issue detection (1 LLM call)
    ↓
Report (.md + optional .pdf)
```

**All 6 branches run simultaneously.** Total time: ~10–15 minutes for a full 6-branch, depth-2 run. Cost with DeepSeek V4: ~$0.10–0.20 USD.

---

## Question Types

CRAM-1 detects the question type automatically and structures the report accordingly. No `--field` flag needed.

| Type | Example Input | What the Report Gets |
|------|--------------|----------------------|
| `pre_op` | "65M portal hypertension, planned Whipple, on rivaroxaban" | CRITICAL ALERTS → RISK STRATIFICATION → PRE-OP CHECKLIST → INTRAOP → POST-OP |
| `research_design` | "I want to design a prospective study on Xpert Ultra in EPTB" | PRIOR ART → STUDY DESIGN → PARAMETERS → MEASUREMENT TOOLS → EVIDENCE GAPS |
| `literature_review` | "What does evidence say about prophylactic IVC filters?" | OVERVIEW → CURRENT EVIDENCE → CONTRADICTIONS → GAPS |
| `clinical_comparison` | "Compare trastuzumab monotherapy vs dual blockade cardiotoxicity" | COMPARISON TABLE → EVIDENCE EACH ARM → RECOMMENDATION |
| `case_discussion` | "58F DM HTN HER2+ breast cancer — cardiac monitoring?" | RISK STRATIFICATION → PROTOCOL → MANAGEMENT → COORDINATION |
| `methodology` | "How should LVEF be monitored during anti-HER2 therapy?" | MEASUREMENT TOOLS → VALIDATED INSTRUMENTS → FREQUENCY → GAPS |

---

## Interactive REPL

Running `cram` without arguments enters the interactive REPL:

```
cram> 58F HER2+ breast cancer, trastuzumab + pertuzumab — cardiac monitoring protocol
[... runs full pipeline ...]

cram> /chat          — enter Q&A against the just-completed research
cram> /list          — browse past sessions
cram> /settings      — show current model config
cram> /clear         — clear screen
cram> /quit          — exit
```

During the research **plan phase** (before DFS starts), you can edit the research plan:

```
Y / Enter    — approve and start research
n            — abort
skip 3       — remove branch 3
add <topic>  — add a new research direction
edit 2 <desc>— change what branch 2 investigates
```

During DFS, type any text and press Enter to queue a new branch mid-research.

### Post-Research Chat

After research completes, CRAM-1 enters Q&A mode against the collected evidence:

```
→ "What if we delay surgery 2 weeks?"
→ "Summarise drug interactions for pharmacy"
→ "What does anaesthesia need to know?"

Chat commands:
  /branches    — list research branches and what they found
  /grep <term> — search raw source texts (PMID, drug name, etc.)
  /search <q>  — run a new targeted search and answer from it
  /report      — show path to the generated report file
  /clear       — reset conversation (keep evidence)
  /quit        — exit chat
```

---

## Sources Searched

**13 sources are searched in parallel on every run** (below). YouTube adds a 14th when `GEMINI_API_KEY` is set, and two post-search enrichment layers (Unpaywall, PMC full-text) fetch open-access full text for the top hits — they don't add new sources, they deepen existing ones.

| Source | Coverage | Notes |
|--------|----------|-------|
| **PubMed / MEDLINE** | Core peer-reviewed literature | Full abstracts via efetch; MeSH expansion; evidence grade from PublicationType |
| **Europe PMC** | European literature + open access | Parallel to PubMed; adds OA status |
| **Semantic Scholar** | 200M+ papers, citation metrics | Influential citation count; better than OpenAlex for signal |
| **ClinicalTrials.gov** | US + international trial registry | NCT IDs, trial status |
| **Cochrane Library** | Systematic reviews / meta-analyses | Highest evidence grade source |
| **CrossRef** | DOI registry | Citation counts, bibliographic data |
| **medRxiv** | Preprints | Labelled `[PREPRINT — not peer reviewed]` |
| **Brave Search** | Scoped web search | Two-pass: unscoped + trusted medical domains |
| **Medical Guidelines** | NICE, WHO, Medscape, AIIMS, ICMR | Direct guideline URL hits |
| **CORE API** | 200M+ open-access repository papers | Unique scope; requires free API key |
| **CTRI** | Indian clinical trial registry | Not on ClinicalTrials.gov; India-specific |
| **OpenFDA** | FDA drug labels | Structured black-box warnings, contraindications |
| **Exa** | Neural + keyword hybrid search | Full-page text extraction for top results |
| **YouTube** *(opt-in, +1)* | Surgical/clinical videos | Requires `GEMINI_API_KEY`; full transcript via Gemini |
| **Unpaywall** *(enrichment)* | Free full-text PDFs by DOI | Post-search; top 3 results |
| **PMC full-text** *(enrichment)* | Open-access full text from PubMed Central | Post-search; escalates verification beyond the abstract |

---

## Model Architecture

Two-tier model config — big model where reasoning matters, fast model for execution:

```
Tier 1 (MODEL_BIG):      Question analysis, BFS planning, synthesis, combined review
Tier 2 (MODEL_RESEARCH): DFS execution, verification, alert classification, compaction
```

**Default (recommended):**
```bash
MODEL_BIG=deepseek/deepseek-v4-pro        # planning + synthesis
MODEL_RESEARCH=deepseek/deepseek-v4-flash # search execution (cheap + fast)
```

Per-phase overrides still work:
```bash
MODEL_SYNTHESIS=deepseek/deepseek-v4-pro
MODEL_VERIFY=deepseek/deepseek-v4-flash
MODEL_ALERT=deepseek/deepseek-v4-flash
# ... etc
```

---

## PDF Export

```bash
# Install PDF dependencies
uv sync --extra pdf

# Run with PDF output
uv run cram -s "..." --pdf
# Generates: report_TIMESTAMP_slug.md
#            report_TIMESTAMP_slug.pdf  ← styled for clinical use
```

PDF is styled for clinical reference: serif font, evidence tables, page numbers, "CRAM-1" footer, page-break-aware sections.

---

## Resume After Interruption / Credit Exhaustion

If a run fails mid-way (credit exhaustion, network error, timeout), CRAM-1 saves pipeline state at each major milestone. Resume exactly where it stopped:

```bash
# If credits ran out, add funds, then:
uv run cram --resume                              # auto-finds most recent interrupted session
uv run cram --resume-session ~/.cram/session_20260526_024343   # specific session

# The error message when credits run out tells you exactly which command to run
```

**What gets checkpointed:**
- After DFS completes: all branch evidence saved to `branch_N.md` files + `pipeline_state.json`
- After unknown-unknowns: UU branch saved
- After contradiction detection: contradiction report saved

Resuming skips all completed stages — if DFS finished before the failure, it won't re-run 60+ LLM calls.

---

## Configuration

```bash
# Required
OPENROUTER_API_KEY=sk-or-v1-...

# Two-tier model architecture (recommended)
MODEL_BIG=deepseek/deepseek-v4-pro
MODEL_RESEARCH=deepseek/deepseek-v4-flash
OPENROUTER_FALLBACK_MODEL=deepseek/deepseek-v4-flash  # fallback on 429

# Research parameters
CRAM_BFS_BRANCHES=6      # parallel research branches (default 6)
CRAM_DFS_DEPTH=2         # follow-up depth per branch (default 2)
CRAM_MAX_WORKERS=6       # parallel source fetches per branch

# Optional integrations
EXA_API_KEY=...              # Exa agentic search — best semantic results
CORE_API_KEY=...             # CORE 200M OA papers (core.ac.uk — free key)
UNPAYWALL_EMAIL=...          # Free full-text by DOI
GEMINI_API_KEY=...           # YouTube video analysis
NCBI_API_KEY=...             # PubMed rate limit 3→10 req/s (free)
BRAVE_API_KEY=...            # Brave Search API (api.search.brave.com)

# Storage
CRAM_DATA_DIR=~/.cram/   # sessions, cache, memory (default)
```

---

## Session Management

```bash
cram --sessions                 # list past research sessions
cram --sessions-search "NSCLC" # full-text search past sessions
cram --list                     # browse sessions for /chat
cram --chat 2                   # load session #2 into Q&A
cram --memory-list              # cross-session agent memory
cram --memory-add "note"
cram --cache-clear              # clear SQLite query cache
cram --cleanup 14               # delete sessions older than 14 days
```

CRAM-1 finds related past sessions at startup (SQLite FTS5) and surfaces them before research begins.

---

## Data Storage

All data lives in `~/.cram/` (configurable via `CRAM_DATA_DIR`):

```
~/.cram/
  query_cache.db          ← SQLite cache of all search queries (avoids re-fetching)
  sessions.db             ← FTS5 index of past sessions for /sessions-search
  MEMORY.md               ← Cross-session agent memory (lessons, key findings)
  session_TIMESTAMP/
    branch_1.md           ← LLM-consolidated evidence per branch (~4–12KB each)
    branch_2.md
    ...
    raw_results.jsonl     ← All raw source snippets (~1.3MB per session)
    pipeline_state.json   ← Checkpoint for resume (stage + branch IDs)
    pending_branches.json ← Branch WAL for crash recovery
    ALERTS.md             ← Critical alerts fired during this session
    research_index.md     ← Branch index
```

**Storage is small by design.** Raw text is stored as snippets (~300 chars), not full papers. Full-text from Unpaywall/Exa is in-memory only during the run. Sessions auto-delete after 7 days. A full run produces ~1.5MB; 100 sessions ≈ 150MB.

---

## Evidence Quality

Every finding goes through three layers before reaching the final report:

1. **Verification** — LLM checks each finding against the raw source snippet. Findings not supported by any source are removed. A "semantic rescue" layer (Layer 3) gives borderline findings a second chance by searching all accumulated raw results.

2. **Citation verification** — After synthesis, every PMID/DOI/NCT in the report is checked against the actual search results. Hallucinated citations are silently removed (not tagged — doctors don't need to see noise).

3. **Combined review** — Single LLM pass adds `[UNSUPPORTED]`, `[CONTRADICTION]`, `⚠️` markers inline AND identifies genuine patient-safety issues (drug interactions, contraindications, missing SOC alternatives).

Evidence grades appear after every claim:
```
🟢🟢 Cochrane SR / meta-analysis    🟢  RCT
🟡🟡 SR of cohort studies           🟡  Cohort / observational
🟠   Case-control                   🔴  Case series / case report
⚫   Expert opinion / consensus      ⚠️  Unverified / unclear
```

---

## Architecture

```
cli.py              ← Entry point: REPL or one-shot. Loads .env FIRST.
run.py              ← Pipeline orchestrator. The only file that knows the sequence.
config.py           ← All constants, env vars, system prompts, evidence grades.

pipeline/
  question_analyzer.py   ← Analyzes question type → dynamic output structure
  intake.py              ← Scenario interrogation, assumptions, clarifications
  bfs.py                 ← Decomposes scenario into N research branches
  dfs.py                 ← Per-branch DFS search + autoDream consolidation
  verifier.py            ← Finding verification + Layer 3 semantic rescue
  alerts.py              ← Batch critical alert classifier (1 LLM call/branch)
  contradiction.py       ← Cross-branch conflict detection
  unknown_unknowns.py    ← Adversarial gap-finding pass
  compactor.py           ← LLM context compression (preserves citations)
  synthesis.py           ← Final report + combined review pass
  chat.py                ← Post-research Q&A
  pdf.py                 ← Markdown → styled PDF export

search/
  base.py                ← SearchBase: SQLite WAL cache, dedup, retry decorator
  pubmed.py              ← esearch + esummary + efetch, MeSH expansion
  brave.py               ← Brave Search API (dual-pass)
  exa.py                 ← Exa neural search + full-page text extraction
  cochrane.py            ← Cochrane REST + NICE fallback
  openfda.py             ← FDA structured drug labels
  ctri.py                ← Indian trial registry
  ... (8 more sources)
  unpaywall.py           ← Post-search full-text enrichment
  pmc_fulltext.py        ← PMC full-text enrichment

provider/
  openrouter.py          ← LLM abstraction: retry, fallback, cost tracking, CreditExhaustedError

memory/
  store.py               ← ResearchMemory, BranchCheckpoint, PipelineCheckpoint
  persistent.py          ← PersistentMemory (cross-session), injection scanning
  session_search.py      ← SQLite FTS5 session indexing

log.py                   ← ANSI helpers + Rich TUI: section(), error_panel(), spin(), stats_panel()
```

---

## Design Decisions and History

### What it was before → what it is now, and why

---

**Profiles / `--field` flag → removed (Round 5, 2026-05)**

*Before:* CRAM-1 had 8 hardcoded specialty profiles (`surgery`, `oncology`, `cardiology`, etc.) as Python dataclasses. Each profile defined output sections, risk tier logic, DDG site scopes, evidence priorities. You had to pass `--field surgery` or the agent would try to auto-detect the field from keywords.

*Problem:* A TB study design question was getting a surgical operating room checklist. Keyword matching (`"vascular"` matching `"cardiovascular"`) was routing things to the wrong profile. A doctor asking "I want to design a study on Xpert Ultra trace results" doesn't want a surgical brief — they want methodology, prior art, parameters.

*Fix:* Replaced profiles entirely with `question_analyzer.py`. On every run, a large model reads the raw scenario and determines: question type, key questions the doctor wants answered, output sections appropriate for that question, synthesis guidance, and practitioner framing. The whole report structure is generated fresh from the question — no hardcoded templates.

---

**Skills system → removed (Round 5, 2026-05)**

*Before:* After each session, CRAM-1 ran an LLM pass to extract "specialty knowledge" and store it in `~/.cram/skills/`. At the start of each session it would load relevant skills and inject them into the synthesis prompt.

*Problem:* The skills were mostly generic medical knowledge the LLM already had. The extraction was an extra LLM call on every run. The loading was based on keyword matching (same fragile system as profiles). The actual impact on report quality was negligible. The file `pipeline/skills.py` still exists as a stub for import compatibility.

*Fix:* Removed from the call chain. Cross-session learning now happens through `PersistentMemory` (which records scenarios, topics, and PMIDs found per session in natural language notes), which is more useful and already existed.

---

**OpenAlex + DOAJ + DrugSafety → removed (2026-05)**

*Before:* 16 sources searched per query, including OpenAlex (citation metadata), DOAJ (open access journals), and a DDG-based drug safety tool.

*Problem:* OpenAlex and Semantic Scholar have ~70% overlap — both return citation metrics on the same academic papers. Semantic Scholar has better signal (influential citation count). DOAJ is a subset of what PubMed + CORE already return. The DrugSafety tool used DuckDuckGo, which is slower and less reliable than Brave Search; OpenFDA already covers structured drug safety data better.

*Fix:* Removed those three. Down to 13 sources with no clinical coverage loss — the remaining sources cover all the same ground.

---

**Per-finding alert classification → batched (Round 5, 2026-05)**

*Before:* After each depth level in DFS, every finding triggered a separate LLM call to the alert classifier. At depth 2 with 5 findings per depth, that's ~10 calls per branch just for alerts.

*Fix:* One LLM call per depth level that classifies all findings at once (`batch_classify_findings`). The prompt lists all findings numbered and asks the classifier to return a JSON array of alert indices. Falls back to per-finding if the batch call fails.

---

**Separate self-review + safety review passes → combined (2026-05)**

*Before:* After synthesis, two sequential LLM calls were made on the full report (both ~20k chars of context):
1. Self-review: adds `[UNSUPPORTED]`, `[CONTRADICTION]`, `⚠️` markers inline
2. Safety review: generates a separate `## Safety Review` section with structured issues

*Problem:* Both passes read the same report. Two calls on 20k chars of context = ~40k input tokens wasted on duplication. The big model is slow and expensive on long inputs.

*Fix:* One call that does both. Returns `{"report": "...", "safety_issues": [...], "ready_for_clinical_use": true}`. A sanity check ensures the LLM didn't accidentally rewrite the report (if output < 70% of input length, discard and keep original). Net result: one fewer big-model call on the most expensive prompt in the pipeline.

---

**Verifier only saw current-depth snippets → now sees all accumulated snippets**

*Before:* At depth 2, the verifier was given only depth-2 search result snippets to validate depth-2 findings. A finding about a topic covered in depth-1 results would get marked REMOVE because the depth-2 snippets from different papers didn't mention it.

*Fix:* Verifier gets snippets from all depths accumulated so far (top 20 results). LLM synthesis still uses only current-depth snippets for focused signal extraction. This significantly reduces false discards.

---

**Minimax M2.7 as default → DeepSeek V4 Pro/Flash (2026-05)**

*Before:* `minimax/minimax-m2.7` was the default for all phases after Claude Sonnet-4.6 started returning 402 (quota exhaustion). Minimax was slow (~20-30s per call) and occasionally returned null content.

*Fix:* DeepSeek V4 Flash as the research model (Tier 2), DeepSeek V4 Pro as the planning/synthesis model (Tier 1). Flash is significantly faster and cheaper ($0.04/$0.16 per M tokens vs Minimax's $0.30/$1.10). A full run now costs ~$0.10–0.20 USD.

---

**No resume after failure → pipeline checkpointing (2026-05)**

*Before:* If a run failed at synthesis (after 60+ LLM calls and 400+ source fetches), you had to start from scratch. The `BranchCheckpoint` WAL only handled branch-level crash recovery, not post-DFS failures.

*Fix:* `PipelineCheckpoint` saves state at each major milestone: after DFS, after unknown-unknowns, after contradiction detection. On a 402 credit exhaustion error, CRAM-1 shows the exact `cram --resume-session PATH` command. On resume, completed stages are skipped — branch evidence is read from `branch_N.md` files, contradiction report from the checkpoint JSON.

---

**Plain ANSI logging → Rich TUI (2026-05)**

*Before:* All output was `print()` with manual ANSI escape codes (`\033[1m`, `\033[32m`). Section headers were manual box-drawing characters. Statistics were plain `print` statements.

*Fix:* Added Rich library. `section(title)` prints a clean horizontal rule. `error_panel(title, body)` shows a red-bordered panel. `spin(label)` shows an animated spinner during LLM calls (on TTY). `stats_panel(elapsed)` shows a clean table. All existing `log()`, `dim()`, `bold()` etc. functions unchanged — Rich is an optional enhancement on top.

---

**`uv run cram` didn't work → pyproject.toml added (2026-05)**

*Before:* The project had only `setup.py`. The venv was created by uv but `uv run cram` failed because there was no `pyproject.toml` for uv to read.

*Fix:* Added `pyproject.toml` declaring the build system and dependencies. The unconventional flat layout (`package_dir={"cram": "."}`) is preserved via `setup.py` being read alongside `pyproject.toml` by setuptools. `uv sync`, `uv run cram`, and `uv run pytest` all work.

---

## Testing

```bash
# Run all tests
uv run pytest tests/ -q

# Specific suites
uv run pytest tests/test_core.py -q     # 146 unit tests
uv run pytest tests/test_e2e.py -q      # 14 end-to-end (mocked network)
uv run pytest -m unit                   # unit only
uv run pytest -m e2e                    # e2e only
```

All HTTP (LLM API + search APIs) is mocked in tests. No real network calls. 160 tests, all passing.

---

## Safety Notes

- Every clinical claim requires a citation (PMID/DOI/NCT/URL)
- Citations are verified against actual search results — hallucinated IDs removed
- Findings marked `[UNSUPPORTED]` or removed if not backed by source snippets
- Critical alerts (black-box warnings, Class I contraindications, mortality-signal drug interactions) are detected in real-time and written to `ALERTS.md` before the branch continues
- Safety review gates the report: if flagged as not ready, a `🚨 NOT READY FOR CLINICAL USE` banner is prepended
- Scenario input is scanned for prompt injection patterns before use
- India formulary warnings for drugs unavailable in India

CRAM-1 is a research assistant, not a clinical decision-making system. It surfaces evidence and flags concerns. Clinical judgment, specialist consultation, and institutional protocols always take precedence.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CRAM-1 is a Python-based AI agent for clinical literature synthesis and research. It searches 13 medical literature sources in parallel (+ optional YouTube and 2 post-search full-text enrichment layers) and synthesizes findings into structured clinical briefs with evidence grading and safety verification. Research strategy is fully dynamic — the LLM determines the research approach entirely from the input scenario with no predefined specialty types.

## Commands

### Installation
```bash
pip install -r requirements.txt
pip install -e .                  # Installs 'cram' CLI entry point
pip install -e ".[gemini]"        # Optional: YouTube/video analysis
pip install -e ".[dev]"           # Optional: pytest + coverage
```

### Running
```bash
cram                          # Interactive REPL (default)
cram -s "clinical scenario"   # Run research directly
cram -s "..." --auto          # Skip plan confirmation
cram -s "..." -b 6 -d 3       # 6 branches, DFS depth 3
cram -s "..." --form          # Structured intake form before research
```

### Interactive REPL
Running `cram` with no arguments enters an interactive prompt (`cram> `).
Type any clinical scenario to start research. Slash commands available:
- `/help` — show available commands
- `/list` — browse past sessions
- `/chat` — load a past session into Q&A chat
- `/settings` — show current configuration
- `/clear` — clear the screen
- `/quit` — exit

### Testing
```bash
pytest                            # All tests
pytest -v --tb=short
pytest -m unit                    # Unit tests only
pytest -m integration             # Integration (mocked network)
pytest -m e2e                     # End-to-end (slow, mocked)
pytest tests/test_specific.py::test_name  # Single test
```

## Environment Setup

Copy `.env.example` to `.env`. Required:
```
OPENROUTER_API_KEY=sk-or-v1-...
```

Optional model overrides per pipeline phase: `MODEL_SYNTHESIS`, `MODEL_VERIFY`, `MODEL_BFS`, `MODEL_DFS`, `MODEL_ALERT`, `MODEL_INTAKE`, `MODEL_UU`, `MODEL_COMPACT`, `MODEL_CONTRADICTION`, `MODEL_SKILLS`, `MODEL_SAFETY`.

Optional features: `GEMINI_API_KEY` (YouTube), `UNPAYWALL_EMAIL` (free full-text), `CORE_API_KEY` (200M papers).

Data stored in `~/.cram/` (configurable via `CRAM_DATA_DIR`).

## Architecture

### Entry Points
- `cli.py` → interactive REPL or direct research run → calls `run.py::run_research()`
- `config.py` — single source of truth for all constants, env vars, and system prompts (220+ lines of prompts)

### Pipeline Sequence (`pipeline/`)
Each stage is a separate module called sequentially by `run.py`:

1. **question_analyzer.py** — analyzes the scenario and generates `bfs_guidance`, `dfs_guidance`, `synthesis_guidance`, `output_sections`, and `practitioner_title` dynamically via LLM
2. **intake.py** — optional structured intake form + scenario interrogation (clarifications/assumptions)
3. **bfs.py** — decomposes scenario into N research branches (default 6), each with primary + followup queries
4. **dfs.py** — depth-first search per branch across 13 sources in parallel, with post-search enrichment
5. **verifier.py** — validates every finding against raw source snippets; flags hallucinations
6. **alerts.py** — detects black-box warnings, contraindications, drug interactions with mortality signals
7. **contradiction.py** — cross-branch contradiction detection with severity scoring
8. **unknown_unknowns.py** — adversarial gap-finding for missing research areas
9. **compactor.py** — compresses long evidence while preserving citations and safety flags
10. **synthesis.py** — assembles clinical brief with evidence grading, risk tier, self-review, and safety review
11. **skills.py** — loads and self-authors reusable specialty knowledge across sessions
12. **chat.py** — post-research interactive Q&A using consolidated evidence

### Search Layer (`search/`)
- `base.py` — `SearchBase` class with SQLite WAL query cache, dedup logic, `@cached_search` and `with_retry` decorators
- `result.py` — `SearchResult` dataclass (not yet adopted by all tools)
- 13 parallel source tools (wired in `pipeline/dfs.py::_PARALLEL_SOURCES`): pubmed, europe_pmc, semantic_scholar, clinical_trials, cochrane, crossref, medrxiv, brave, guidelines, core_api, ctri, openfda, exa. YouTube is added separately (opt-in, needs GEMINI_API_KEY). Post-search enrichment: unpaywall, pmc_fulltext. NOTE: `search/open_alex.py`, `doaj.py`, `ddg.py`, `fda_drug.py` exist but are NOT wired into the pipeline (dead code, referenced only by tests)
- Sources use parallel workers (`CRAM_MAX_WORKERS`, default 6)

### LLM Provider (`provider/openrouter.py`)
- Single provider abstraction over OpenRouter API
- Phase-based model selection (each pipeline stage can use a different model)
- Retry logic with exponential backoff + automatic fallback to `OPENROUTER_FALLBACK_MODEL`
- Token tracking and session statistics

### Profiles (`profiles/`)
- Profiles are removed — all research guidance is generated dynamically by `pipeline/question_analyzer.py`
- `profiles/base.py` and `profiles/registry.py` are empty stubs kept for import compatibility
- Field-specific constants (`INDIA_NOTE`, `GENERIC_DDG_SITES`) live in `config.py`
- Sessions are indexed under `field="general"` in memory

### Memory (`memory/`)
- `store.py` — `ResearchMemory` (per-session) + `BranchCheckpoint` (WAL for crash recovery)
- `persistent.py` — `PersistentMemory` (cross-session learned knowledge) + `scan_for_injection()`
- `session_search.py` — SQLite FTS5-backed session indexing for past session reuse

### Key Design Patterns
- All system prompts live in `config.py`, not inline in pipeline modules
- Research strategy (branch structure, output sections, practitioner framing) is determined by `question_analyzer.py` via LLM from the raw scenario — no hardcoded specialty types
- Search results are cached in SQLite to avoid redundant API calls across sessions
- Injection security: `config.py` contains regex patterns to sanitize user inputs before prompt construction
- Evidence grading uses emoji scale (🟢🟢 to ⚠️) defined in `config.py`
- Every LLM claim in synthesis must be backed by a cited source (enforced in verifier)

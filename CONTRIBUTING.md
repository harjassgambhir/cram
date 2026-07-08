# Contributing to CRAM-1

CRAM-1 is a clinical research assistant used by doctors to synthesize medical literature before complex cases. Contributions that improve evidence quality, citation accuracy, source coverage, or clinical safety are welcome.

---

## Before You Start

Read the README and understand the pipeline sequence: question analysis → BFS → DFS → verification → synthesis. Most improvements touch one stage without needing to understand all of them.

The one constraint that overrides everything else: **no hallucination, no dropped safety signals**. If a change improves speed or structure but risks losing a drug interaction or dosing number, it does not ship.

---

## Development Setup

```bash
# Requires Python 3.11+ and uv
git clone https://github.com/harjass/medagent.git
cd medagent

uv sync
cp .env.example .env
# Add OPENROUTER_API_KEY to .env

# Run tests
uv run pytest tests/ -q
```

All 160 tests should pass before and after any change.

---

## What's Most Useful

**New search sources** — `search/` follows a simple pattern: `@cached_search("SourceName")` decorator, returns `list[dict]` with `source`, `title`, `url`, `snippet`, and optionally `pmid`, `doi`, `year`. Wire into `pipeline/dfs.py::_TIER1` or `_TIER2`. Add tests in `tests/test_search.py`.

**Verifier improvements** — `pipeline/verifier.py` is the gatekeeper. False discards (legitimate findings dropped) and false passes (hallucinations let through) are both failure modes. The current Layer 3 semantic rescue handles many borderline cases but is not perfect.

**Citation grounding** — `pipeline/synthesis.py::_verify_report_citations()` strips hallucinated PMIDs/DOIs/NCTs. Edge cases (unusual DOI formats, preprint IDs) are a known gap.

**India-specific coverage** — Indian clinical trial registry (CTRI) is already integrated. IndMED, AIIMS Journal, NMC Clinical Guidelines, ICMR Guidelines, and Medknow/Wolters Kluwer India are not. Indian formulary integration (brand names ↔ generics, essential-list tier) is planned for v8.

---

## What to Avoid

- Changing the BFS/DFS core loop without a concrete quality improvement to show for it
- Adding LLM calls to the hot path without a clear justification — each call adds latency and cost
- Removing existing safety checks or verification steps
- Adding hardcoded specialty logic — question type detection and output structure are intentionally dynamic (see `pipeline/question_analyzer.py`)

---

## Pull Requests

- One logical change per PR
- Tests for any new search source or pipeline stage
- If you're adding a new API dependency, document the key acquisition in `.env.example`
- Run `uv run pytest tests/ -q` — all 160 tests must pass

For bugs, open an issue first if the fix is non-obvious. For new sources, a PR with a working implementation and tests is enough.

---

## A Note on the Domain

CRAM-1 outputs are read by doctors making clinical decisions. If you are unsure whether a change is safe, it is not. The bar for shipping something that touches evidence handling, citation verification, or safety alerts is high — and that is intentional.

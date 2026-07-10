# CRAM Benchmarks — running log, limitations, and roadmap

This is CRAM's honest scorecard. Every claim CRAM makes about itself ("retrieves
the right evidence", "removes fabricated findings") is turned into a number here,
measured against public gold standards, and **tracked over time** so that when we
say an update improved something, the number proves it on the *same* dataset.

The rule: we only claim an improvement if a row below moves in the right direction
against the identical dataset and method. Regressions get logged too.

---

## Running results log

Each row is a benchmark run at a specific commit. `full` = the real CRAM pipeline;
`search-only` = the no-LLM retrieval floor. See "How these are measured" below.

| Date | Commit | Cochrane recall — full<br>(micro / macro) | Cochrane recall — search-only<br>(micro / macro) | Verifier catch / false-discard | What changed |
|------|--------|:--:|:--:|:--:|--------------|
| 2026-07-10 | `c9800c4` | **24.8% / 28.5%** | 16.3% / 19.9% | **100% / 0%** | Baseline: benchmark established (5 CLEF-TAR reviews, 129 included studies; 3 planted-error fixtures, 18 claims). Full run had 117 PubMed 429s (no `NCBI_API_KEY`). |

> To add a row: re-run the benchmarks (below), commit the resulting
> `eval/results/baseline_*.json`, and append a line with the new commit + numbers
> and a one-line note on what changed. Do not overwrite old rows — the history is
> the point.

Per-review detail for the baseline lives in
[`results/baseline_full_pipeline.json`](results/baseline_full_pipeline.json) and
[`results/baseline_search_only.json`](results/baseline_search_only.json).

---

## How these are measured (and how to replicate independently)

Fully reproducible — no private data. Gold sets are fetched from public sources.

```bash
uv run python -m cram.eval.build_dataset            # fetch CLEF-TAR gold (no key)
uv run python -m cram.eval.cochrane_recall          # search-only floor (no key, free)
uv run python -m cram.eval.cochrane_recall --full   # full pipeline (needs OPENROUTER_API_KEY)
uv run python -m cram.eval.planted_errors           # verifier catch rate (needs OPENROUTER_API_KEY)
```

- **Cochrane recall** = `|retrieved PMIDs ∩ review's included PMIDs| / |included|`.
  Gold is [CLEF eHealth TAR 2018 Task 2](https://github.com/CLEF-TAR/tar) — real
  Cochrane reviews with per-study inclusion labels. Anyone can fetch the same
  qrels and reproduce the gold set.
- **Verifier catch rate** = planted fabrications removed / total planted;
  **false-discard** = genuine findings wrongly removed / total genuine.

**Independently replicable?**
- `build_dataset` and `search-only` recall: **yes, exactly** — deterministic, no
  key, no LLM. Same inputs → same numbers.
- `--full` recall and `planted_errors`: **directionally, not bit-for-bit** — they
  call an LLM, so numbers vary run-to-run and with the configured model. Report
  the model + commit alongside any number (the baseline used
  `deepseek-v4-pro`/`deepseek-v4-flash`).

---

## Known limitations (why these numbers are floors, not ceilings)

1. **PMID-only matching.** Recall counts only PubMed + Europe PMC hits, the two
   sources that emit PMIDs. DOI-only sources (Semantic Scholar, Crossref, CORE,
   Exa, medRxiv) widen real coverage but are invisible to this metric. True recall
   is higher than reported.
2. **PubMed rate-limiting depresses `--full`.** Without an `NCBI_API_KEY`, eutils
   throttles at ~3 req/s; the parallel pipeline blew past it (117× HTTP 429 in the
   baseline run), so some searches returned nothing. Set `NCBI_API_KEY` (free, 10
   req/s) and full-mode recall should rise — that is itself a hypothesis to test in
   the next row.
3. **Small seed set.** 5 reviews / 129 included studies, all *diagnostic-test-
   accuracy* reviews from CLEF-TAR 2018. Not yet representative of intervention or
   prognosis reviews. Widen via `build_dataset.py::SEED_REVIEWS`.
4. **Small planted-error set.** 3 fixtures / 18 claims. 100% catch is encouraging
   but n is tiny; the fabrications are deliberately clear-cut. Harder,
   subtler planted errors (e.g. a real PMID with a slightly-wrong effect size) are
   the next stress test.
5. **Search-only queries are naive.** Derived from the review title with no MeSH
   expansion or PICO decomposition — deliberately, to measure a floor.
6. **LLM nondeterminism.** `--full` and `planted_errors` vary run-to-run; treat
   single runs as estimates, not fixed values.

---

## What we're working on — each tied to the number it should move

| Planned work | Metric it should move | Hypothesis |
|--------------|-----------------------|------------|
| Set/document `NCBI_API_KEY` in full runs | Cochrane recall (full) | Removes the 429 throttle; expect the TB review to recover toward its 78% floor |
| DOI→PMID resolution before matching | Cochrane recall (both) | Counts DOI-only hits; measured recall rises toward true recall |
| Systematic-review anchoring (find the SR first, search after its cutoff) | Cochrane recall (full) | Changes *what* we search for; biggest expected raw gain |
| PICO decomposition + MeSH expansion | Cochrane recall (both) | Catches papers naive keywords miss |
| Citation-graph traversal from key trials | Cochrane recall (full) | Surfaces included studies keyword search never reaches |
| Harder planted-error fixtures | Verifier catch rate | Stress-tests the verifier beyond obvious fabrications |
| Expand to intervention/prognosis reviews | Cochrane recall (both) | Generalises the number beyond DTA reviews |

When one of these ships, we re-run, add a row, and the delta is the proof it worked.

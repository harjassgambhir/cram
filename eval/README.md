# CRAM Evaluation Harness

CRAM asserts two properties it should be able to *measure*: that it retrieves the
right evidence, and that it removes fabricated claims. This directory turns both
into numbers.

| Benchmark | Question | Metric | Gold source |
|-----------|----------|--------|-------------|
| **Cochrane recall** | Does CRAM retrieve the studies a real Cochrane review included? | recall = found / included | [CLEF eHealth TAR 2018](https://github.com/CLEF-TAR/tar) |
| **Planted errors** | Does the verifier remove fabricated findings? | catch rate; false-discard rate | Hand-built fixtures |

---

## 1. Cochrane recall

Retrieval is the ceiling on everything downstream — you cannot synthesise evidence
you never found. We measure recall against **CLEF eHealth TAR 2018 (Task 2)**, the
standard IR gold standard: real Cochrane reviews where every candidate study is
labelled included / excluded after the review team's full-text screening. The
included set is our ground truth.

```bash
uv run python -m cram.eval.build_dataset       # fetch gold → datasets/cochrane_reviews.jsonl
uv run python -m cram.eval.cochrane_recall     # search-only (no LLM, no key, free)
uv run python -m cram.eval.cochrane_recall --full   # real pipeline (needs API key)
```

**Two modes:**

- **search-only** (default) — runs CRAM's PubMed + Europe PMC tools on queries
  derived deterministically from the review title. No LLM, fully reproducible.
  Measures the raw retrieval **floor**.
- **`--full`** — runs the real `run_research` pipeline per review (LLM-driven BFS
  query generation across all 13 sources) and harvests retrieved PMIDs from the
  session's `raw_results.jsonl`. Measures the whole system. Costs API credits.

Recall is matched on PMID, and only PubMed + Europe PMC emit PMIDs, so DOI-only
sources (Semantic Scholar, Crossref, CORE, …) are not counted — the reported
number is a genuine floor, not a ceiling.

### Baseline result (5 reviews, 129 included studies)

Full pipeline vs the no-LLM search-only floor. Per-review JSON:
[`results/baseline_full_pipeline.json`](results/baseline_full_pipeline.json),
[`results/baseline_search_only.json`](results/baseline_search_only.json).

| Review | Topic | Full pipeline | Search-only floor |
|--------|-------|--------------:|------------------:|
| CD010705 | GenoType MTBDRsl for 2nd-line anti-TB resistance | 50% (9/18) | 78% (14/18) |
| CD009135 | Rapid tests for visceral leishmaniasis | 21% (4/19) | 11% (2/19) |
| CD010276 | Diagnostic tests for oral cancer | 17% (4/24) | 0% (0/24) |
| CD009185 | Procalcitonin/CRP/ESR for paediatric pyelonephritis | 43% (10/23) | 0% (0/23) |
| CD007394 | Galactomannan for invasive aspergillosis | 11% (5/45) | 11% (5/45) |
| **Pooled** | | **micro 24.8%, macro 28.5%** | micro 16.3%, macro 19.9% |

**Reading this honestly:** the full pipeline lifts pooled recall from 16.3% → 24.8%
and rescues broad topics that title-only search missed entirely (oral cancer 0→17%,
pyelonephritis 0→43%). It *dropped* on the narrow TB review (78→50%) because that
run hit PubMed rate-limiting (117× HTTP 429 with no `NCBI_API_KEY`) — so 24.8% is a
throttled floor. The running version log, limitations, and roadmap are in
[`BENCHMARKS.md`](BENCHMARKS.md).

---

## 2. Planted-error catch rate

Turns CRAM's core safety claim — "unsupported findings are removed" — into a
number. Each fixture pairs real source snippets with genuinely-supported (`true`)
findings and fabricated (`planted`) ones: invented effect sizes, made-up PMIDs,
unsupported conclusions. Each finding is passed through the real verifier alone
(semantic rescue disabled) so attribution is exact.

```bash
uv run python -m cram.eval.planted_errors      # needs an API key (verifier = LLM)
```

- **catch_rate** — planted fabrications correctly removed / total planted (want high)
- **false_discard_rate** — true findings wrongly removed / total true (want low)

Fixtures live in [`datasets/planted_errors.jsonl`](datasets/planted_errors.jsonl);
add your own to grow the set.

---

## Extending the gold set

`build_dataset.py::SEED_REVIEWS` lists the Cochrane review IDs pulled from CLEF-TAR.
Add any review ID present in the 2018 Task 2 qrels to widen coverage. For a larger,
harder benchmark, point it at the CLEF-TAR 2017/2019 collections or the full DTA /
Intervention qrels.

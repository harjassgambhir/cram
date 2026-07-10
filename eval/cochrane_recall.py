"""eval/cochrane_recall.py

Cochrane-recall benchmark — the headline empirical metric for CRAM.

Question it answers: *when a real Cochrane review team decided which studies to
include, how many of those studies does CRAM's search actually surface?* Recall
is the ceiling on synthesis quality — you cannot summarise evidence you never
retrieved.

  recall = |retrieved_pmids ∩ gold_included_pmids| / |gold_included_pmids|

Two modes:

  search-only (default)  No LLM, no API key, ~free. Runs CRAM's PubMed +
                         Europe PMC tools on queries derived from the review
                         title. Measures the raw retrieval floor and is fully
                         reproducible in CI-like conditions.

  --full                 Runs the real CRAM pipeline (run_research) per review,
                         then reads retrieved PMIDs from the session's
                         raw_results.jsonl. Measures the whole system including
                         LLM-driven BFS query generation. Costs API credits.

Gold data: eval/datasets/cochrane_reviews.jsonl (see build_dataset.py).
Only PubMed + Europe PMC return PMIDs, so recall is measured against those two
bibliographic sources; DOI-only sources (Semantic Scholar, Crossref, …) widen
coverage in a real run but are not counted here. Recall is therefore a floor.

Run:
  uv run python -m cram.eval.build_dataset            # once, to fetch gold
  uv run python -m cram.eval.cochrane_recall          # search-only, all reviews
  uv run python -m cram.eval.cochrane_recall --review CD010705 --max-results 60
  uv run python -m cram.eval.cochrane_recall --full   # real pipeline (needs API key)
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DATASET = Path(__file__).parent / "datasets" / "cochrane_reviews.jsonl"
RESULTS_DIR = Path(__file__).parent / "results"

_STOP = {
    "the", "of", "for", "and", "in", "to", "a", "an", "with", "on", "by",
    "diagnostic", "accuracy", "detection", "diagnosis", "screening", "test",
    "tests", "patients", "suspected", "using", "versus", "vs",
}


def load_dataset(path: Path = DATASET) -> list[dict]:
    if not path.exists():
        sys.exit(f"Dataset not found: {path}\nRun: uv run python -m cram.eval.build_dataset")
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def queries_from_title(title: str) -> list[str]:
    """Derive a small set of PubMed keyword queries from a review title.

    Deterministic (no LLM) so search-only mode is reproducible. Handles the
    common "<intervention> for [the] ... of <condition>" shape.
    """
    title = title.strip().rstrip(".")
    queries = [title]  # esearch term-maps a full title reasonably well
    m = re.search(r"^(.*?)\bfor\b(.*)$", title, flags=re.IGNORECASE)
    if m:
        intervention = m.group(1).strip(" ,")
        condition = re.sub(r"^(the|detection|diagnosis|screening)\s+of\s+",
                           "", m.group(2).strip(" ,"), flags=re.IGNORECASE)
        if intervention:
            queries.append(intervention)
        if intervention and condition:
            # keyword-only intervention + condition
            kws = [w for w in re.findall(r"[A-Za-z0-9®*-]+", f"{intervention} {condition}")
                   if w.lower() not in _STOP and len(w) > 2]
            if kws:
                queries.append(" ".join(kws[:8]))
    # dedup, preserve order
    seen, out = set(), []
    for q in queries:
        k = q.lower()
        if q and k not in seen:
            seen.add(k)
            out.append(q)
    return out


def _retrieved_pmids_search_only(title: str, max_results: int) -> set[str]:
    from cram.search.pubmed import tool_pubmed
    from cram.search.europe_pmc import tool_europe_pmc
    pmids: set[str] = set()
    for q in queries_from_title(title):
        for tool in (tool_pubmed, tool_europe_pmc):
            try:
                for r in tool(q, max_results=max_results):
                    pm = str(r.get("pmid", "")).strip()
                    if pm and pm not in ("N/A", "None"):
                        pmids.add(pm)
            except Exception as e:  # a flaky source must not sink the run
                print(f"    ! {tool.__name__}('{q[:40]}') failed: {e}", file=sys.stderr)
    return pmids


def _retrieved_pmids_full(title: str) -> set[str]:
    """Run the real pipeline and harvest PMIDs from the session raw results."""
    from cram import config as cfg
    from cram.run import run_research
    before = set(cfg.DATA_DIR.glob("session_*"))
    run_research(title, auto=True, enter_chat=False, pdf=False)
    after = set(cfg.DATA_DIR.glob("session_*"))
    new = sorted(after - before, key=lambda p: p.stat().st_mtime)
    if not new:
        return set()
    raw = new[-1] / "raw_results.jsonl"
    pmids: set[str] = set()
    if raw.exists():
        for line in raw.read_text(encoding="utf-8").splitlines():
            try:
                pm = str(json.loads(line).get("pmid", "")).strip()
                if pm and pm not in ("N/A", "None"):
                    pmids.add(pm)
            except Exception:
                continue
    return pmids


def evaluate(reviews: list[dict], full: bool, max_results: int) -> dict:
    per_review = []
    for rev in reviews:
        gold = set(rev["included_pmids"])
        title = rev["title"]
        print(f"\n▶ {rev['review_id']} — {title[:70]}")
        print(f"  gold included: {len(gold)}")
        retrieved = (_retrieved_pmids_full(title) if full
                     else _retrieved_pmids_search_only(title, max_results))
        hit = gold & retrieved
        recall = len(hit) / len(gold) if gold else 0.0
        print(f"  retrieved: {len(retrieved)} pmids | "
              f"found {len(hit)}/{len(gold)} included → recall {recall:.0%}")
        per_review.append({
            "review_id": rev["review_id"],
            "title": title,
            "n_included": len(gold),
            "n_retrieved": len(retrieved),
            "n_found": len(hit),
            "recall": round(recall, 4),
            "found_pmids": sorted(hit),
        })

    micro_num = sum(r["n_found"] for r in per_review)
    micro_den = sum(r["n_included"] for r in per_review)
    macro = (sum(r["recall"] for r in per_review) / len(per_review)
             if per_review else 0.0)
    summary = {
        "mode": "full" if full else "search-only",
        "max_results": None if full else max_results,
        "n_reviews": len(per_review),
        "micro_recall": round(micro_num / micro_den, 4) if micro_den else 0.0,
        "macro_recall": round(macro, 4),
        "total_included": micro_den,
        "total_found": micro_num,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "per_review": per_review,
    }
    return summary


def main():
    ap = argparse.ArgumentParser(description="CRAM Cochrane-recall benchmark")
    ap.add_argument("--full", action="store_true",
                    help="run the real pipeline (needs API key, costs credits)")
    ap.add_argument("--review", help="run a single review by ID (e.g. CD010705)")
    ap.add_argument("--max-results", type=int, default=50,
                    help="results per source per query in search-only mode")
    ap.add_argument("--out", help="write JSON summary to this path")
    args = ap.parse_args()

    if args.full:  # real pipeline needs the API key from .env
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

    reviews = load_dataset()
    if args.review:
        reviews = [r for r in reviews if r["review_id"] == args.review]
        if not reviews:
            sys.exit(f"No review {args.review} in dataset")

    summary = evaluate(reviews, full=args.full, max_results=args.max_results)

    print("\n" + "=" * 60)
    print(f"MODE: {summary['mode']}   reviews: {summary['n_reviews']}")
    print(f"MICRO recall (pooled studies): {summary['micro_recall']:.1%} "
          f"({summary['total_found']}/{summary['total_included']})")
    print(f"MACRO recall (avg per review): {summary['macro_recall']:.1%}")
    print("=" * 60)

    out = Path(args.out) if args.out else (
        RESULTS_DIR / f"recall_{summary['mode']}_"
        f"{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nWrote summary → {out}")


if __name__ == "__main__":
    main()

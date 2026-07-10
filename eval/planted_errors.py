"""eval/planted_errors.py

Planted-error benchmark — measures the verifier's hallucination catch rate.

CRAM's central safety claim is "every finding is checked against raw source text
and unsupported ones are removed." This turns that claim into a number.

Method: for each fixture we have (a) a block of raw source snippets, (b) a set
of TRUE findings that are genuinely supported by those snippets, and (c) a set
of PLANTED findings — fabricated claims (invented effect sizes, made-up PMIDs,
unsupported conclusions) that the snippets do NOT support. Each finding is passed
through the real verifier individually (so attribution is exact).

  catch_rate        = planted findings correctly REMOVED / total planted   (want high)
  false_discard     = true findings wrongly REMOVED     / total true       (want low)

catch_rate is the safety metric; false_discard is the cost of being strict.

Needs an API key (the verifier is an LLM call). Semantic rescue is disabled here
(memory=None) so we measure the verifier itself, not the rescue layer.

Run:
  uv run python -m cram.eval.planted_errors
  uv run python -m cram.eval.planted_errors --out eval/results/planted.json
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DATASET = Path(__file__).parent / "datasets" / "planted_errors.jsonl"
RESULTS_DIR = Path(__file__).parent / "results"


def load_fixtures(path: Path = DATASET) -> list[dict]:
    if not path.exists():
        sys.exit(f"Fixture file not found: {path}")
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _kept(finding: str, snippets: str) -> bool:
    """True if the verifier KEEPS this single finding (memory=None → no rescue)."""
    from cram.pipeline.verifier import verify_findings
    return len(verify_findings([finding], snippets, label="planted-eval",
                               memory=None)) > 0


def evaluate(fixtures: list[dict]) -> dict:
    planted_total = planted_caught = 0
    true_total = true_dropped = 0
    details = []

    for fx in fixtures:
        snippets = fx["snippets"]
        for claim in fx.get("planted", []):
            planted_total += 1
            caught = not _kept(claim, snippets)
            planted_caught += int(caught)
            if not caught:
                details.append({"type": "planted_MISSED", "claim": claim})
        for claim in fx.get("true", []):
            true_total += 1
            dropped = not _kept(claim, snippets)
            true_dropped += int(dropped)
            if dropped:
                details.append({"type": "true_DROPPED", "claim": claim})

    summary = {
        "planted_total": planted_total,
        "planted_caught": planted_caught,
        "catch_rate": round(planted_caught / planted_total, 4) if planted_total else 0.0,
        "true_total": true_total,
        "true_dropped": true_dropped,
        "false_discard_rate": round(true_dropped / true_total, 4) if true_total else 0.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "misses": details,
    }
    return summary


def main():
    ap = argparse.ArgumentParser(description="Verifier hallucination catch-rate")
    ap.add_argument("--out", help="write JSON summary to this path")
    args = ap.parse_args()

    try:  # verifier is an LLM call — load the API key from .env
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    summary = evaluate(load_fixtures())
    print("\n" + "=" * 60)
    print(f"Planted-error catch rate: {summary['catch_rate']:.1%} "
          f"({summary['planted_caught']}/{summary['planted_total']} fabrications removed)")
    print(f"False-discard rate:       {summary['false_discard_rate']:.1%} "
          f"({summary['true_dropped']}/{summary['true_total']} true findings wrongly dropped)")
    print("=" * 60)

    out = Path(args.out) if args.out else (
        RESULTS_DIR / f"planted_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nWrote summary → {out}")


if __name__ == "__main__":
    main()

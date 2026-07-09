"""eval/build_dataset.py

Build the Cochrane-recall benchmark dataset from the CLEF eHealth TAR 2018
collection (Task 2 — Technology-Assisted Reviews).

Why CLEF-TAR: it is the standard, peer-reviewed gold standard for exactly this
task. Each entry is a real Cochrane review with, for every candidate study, a
label of whether it was ultimately *included* in the review after full-text
screening. That inclusion set is our ground truth for "the studies a skilled
human review team decided were relevant." Using it means our recall numbers are
comparable to the information-retrieval literature instead of a hand-typed list.

  Kanoulas, Li, Azzopardi, Spijker (2018). "CLEF 2018 Technologically Assisted
  Reviews in Empirical Medicine Overview." CEUR-WS Vol-2125.
  Data: https://github.com/CLEF-TAR/tar

Output: eval/datasets/cochrane_reviews.jsonl — one review per line:
  {
    "review_id":      "CD010705",           # Cochrane review number
    "title":          "...",                 # review title (the clinical question)
    "boolean_query":  "...",                 # the review team's MEDLINE query
    "included_pmids": ["7072537", ...],       # gold: studies included after screening
    "n_included":     18,
    "n_screened":     114
  }

Run:  uv run python -m cram.eval.build_dataset
"""
import json
import sys
import urllib.request
from pathlib import Path

RAW = "https://raw.githubusercontent.com/CLEF-TAR/tar/master/2018-TAR/Task2/Training"
QRELS_URL = f"{RAW}/qrels/full.train.content.2018.qrels"
TOPIC_URL = f"{RAW}/topics/{{review_id}}"

# Seed set: a spread of real Cochrane diagnostic-test-accuracy reviews with
# moderate included-study counts. Several deliberately hit CRAM's India focus
# (TB drug-resistance, visceral leishmaniasis, oral cancer).
SEED_REVIEWS = [
    "CD010705",  # GenoType MTBDRsl for 2nd-line anti-TB drug resistance (TB / India)
    "CD009135",  # Rapid tests for visceral leishmaniasis (kala-azar / India)
    "CD010276",  # Diagnostic tests for oral cancer (India: high oral-cancer burden)
    "CD009185",  # Procalcitonin/CRP/ESR for acute pyelonephritis in children
    "CD007394",  # Galactomannan for invasive aspergillosis
]

OUT = Path(__file__).parent / "datasets" / "cochrane_reviews.jsonl"


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "cram-eval/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def _parse_qrels(text: str) -> dict[str, dict[str, list[str]]]:
    """review_id -> {'included': [pmids], 'screened': [pmids]} from TAR qrels.

    Line format: `<review_id> 0 <pmid> <relevance>` where relevance 1 == included.
    """
    out: dict[str, dict[str, list[str]]] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        review_id, _, pmid, rel = parts
        d = out.setdefault(review_id, {"included": [], "screened": []})
        d["screened"].append(pmid)
        if rel == "1":
            d["included"].append(pmid)
    return out


def _parse_title_query(topic_text: str) -> tuple[str, str]:
    title, query_lines, in_query = "", [], False
    for line in topic_text.splitlines():
        if line.startswith("Title:"):
            title = line[len("Title:"):].strip()
        elif line.startswith("Query:"):
            in_query = True
        elif in_query:
            query_lines.append(line.strip())
    return title, "\n".join(l for l in query_lines if l).strip()


def build(review_ids=SEED_REVIEWS) -> int:
    print(f"Fetching qrels: {QRELS_URL}")
    qrels = _parse_qrels(_fetch(QRELS_URL))

    rows = []
    for rid in review_ids:
        if rid not in qrels:
            print(f"  ! {rid} not in qrels — skipping", file=sys.stderr)
            continue
        topic = _fetch(TOPIC_URL.format(review_id=rid))
        title, bquery = _parse_title_query(topic)
        included = sorted(set(qrels[rid]["included"]))
        rows.append({
            "review_id": rid,
            "title": title,
            "boolean_query": bquery,
            "included_pmids": included,
            "n_included": len(included),
            "n_screened": len(set(qrels[rid]["screened"])),
        })
        print(f"  ✓ {rid}: {len(included)} included / "
              f"{len(set(qrels[rid]['screened']))} screened — {title[:60]}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(rows)} reviews → {OUT}")
    return len(rows)


if __name__ == "__main__":
    build()

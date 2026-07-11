# Example reports

Real, unedited CRAM output. The report **is** the product, so here it is without
needing an API key or 20 minutes — read one and judge for yourself.

Competitor tools (OpenEvidence, Elicit, Consensus) demo clean, single-axis
questions on well-trodden topics — *"Does zinc reduce cold duration?"*, *"SGLT2i
for HF in non-diabetics?"*. These examples take that kind of question and **10x
the difficulty**: the gnarly, multi-constraint, safety-critical scenarios a real
clinician actually faces, chosen to exercise what CRAM does that a search box
doesn't — safety alerts, contradiction detection, evidence grading, India-specific
drug access, and structured briefs.

| Report | Type | The 10x scenario | What it shows off |
|--------|------|------------------|-------------------|
| [01 — SGLT2i in complex HFpEF](reports/01-sglt2i-complex-hfpef.md) | clinical comparison | Frail 74M, HFpEF + CKD 3b + recurrent candidiasis: empagliflozin vs dapagliflozin vs withhold, with India cost/access | Weighs benefit vs eDKA/mycotic/frailty risk; reaches a defensible *"reasonable not to start"* — the nuance a naive tool misses |
| [02 — Peri-operative multi-morbidity](reports/02-periop-tkr-multimorbidity.md) | pre-op brief | 68F for knee replacement on 3 DMARDs, SGLT2i + metformin, and apixaban for prior PE | Which drug to hold/bridge/continue and *when*; euglycemic-DKA + anticoagulation + infection hazards in one plan |
| [03 — India TB pragmatic RCT](reports/03-tb-pragmatic-rct-india.md) | research design | Design a pragmatic India trial of shortened all-oral BPaLM vs SoC for pre-XDR TB, MTBDRsl-guided | Full PICO + sample-size calc; **caught that the premise itself is clinically wrong** (BPaLM's moxifloxacin is contraindicated in FQ-resistant pre-XDR TB) |

Each report was verified before being committed — citations spot-checked live
against PubMed, safety content confirmed, structure and rendering reviewed. The
pass/fail log with per-report checks, runtime, and cost is in
[`RESULTS.md`](RESULTS.md); the exact prompts are in [`scenarios.md`](scenarios.md).

> These are literature-synthesis briefs for clinical *reference*, not treatment
> advice. Every claim must be checked against its cited source. See the repo README
> disclaimer.

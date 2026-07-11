# Example runs — verification log

Each example was produced by the real CRAM pipeline (`uv run cram -s "..." --auto
--no-chat`) with `deepseek-v4-pro` (planning/synthesis) + `deepseek-v4-flash`
(research), no `NCBI_API_KEY` set. A report is only kept here if it **passes**
the checks below.

**Verification checks**
1. **Answers the ask** — every part of the prompt is addressed with a structured section.
2. **Citations are real** — headline PMIDs/DOIs spot-checked live against PubMed/Crossref (not hallucinated).
3. **Safety handled** — genuine hazards surfaced (alerts / critical section), none fabricated.
4. **Honest gaps** — missing evidence is marked `NO EVIDENCE FOUND`, not invented.
5. **Renders cleanly** — headings, tables, and any mermaid diagram display correctly.

**Authenticity note.** Reports are verbatim pipeline output. The only post-hoc
touches are (a) the pipeline's own deterministic `_fix_mermaid_fences` normaliser
applied to two reports generated before that fix shipped, and (b) removal of a
single non-English word the model code-switched into one report. Content, claims,
citations, and structure are unedited.

---

## 01 — SGLT2i in complex HFpEF (`clinical_comparison`)
Competitor baseline (OpenEvidence): *"latest evidence on SGLT2 inhibitors for heart failure in non-diabetic patients."*
10x: frail 74M, HFpEF + CKD 3b (eGFR 34) + recurrent candidiasis; empagliflozin vs dapagliflozin vs withhold, with India cost/access.

| | |
|--|--|
| Runtime / cost | 22m 54s · $0.045 · 657 source fetches · 88 LLM calls |
| Citations checked | 37062851 (EMPEROR-Preserved CKD), 30766827 (SGLT2i genital infections, *Indian J Endocrinol*), 39518647, 35308676 — **all real** |
| Safety | CRITICAL ALERTS section surfaced euglycemic DKA, Fournier's gangrene, volume-depletion/falls |
| Standout | Reached a defensible *"reasonable not to start"* default for a frail patient — the nuance a naive tool misses |
| Defects found | Bare mermaid block (fixed by pipeline normaliser); one code-switched word (removed) |
| **Verdict** | ✅ **PASS** |

## 02 — Multi-morbidity peri-operative planning (`pre_op`)
Competitor baseline: single-drug peri-op / dosing question.
10x: 68F for TKR on MTX + leflunomide + prednisolone, empagliflozin + metformin, prior PE on apixaban.

| | |
|--|--|
| Runtime / cost | 22m 47s · $0.068 · 818 source fetches · 87 LLM calls |
| Citations checked | 35732511 (2022 ACR/AAHKS peri-op DMARD guideline), 30152137 (Cochrane dexamethasone), 10.1161/cir.0000000000000477 (AHA NOAC statement) — **all real** |
| Safety | Dedicated "potentially fatal complications" table (euDKA, adrenal crisis, thromboembolism, PJI, haemorrhage); safety review caught 7 issues incl. its *own* over-dosed steroid recommendation |
| Standout | Flagged subtle lethal hazards a search box misses: leflunomide→apixaban CYP2C9 interaction, and empagliflozin *masking* both hyperglycaemia and adrenal-crisis signs |
| Defects found | Empty "Scenario Notes" section; two incomplete citation stubs (`Takemura 2025:`) — left as-is (honestly marked, not hallucinated) |
| **Verdict** | ✅ **PASS** |

## 03 — India TB pragmatic RCT (`research_design`)
Competitor baseline (Elicit): *"recent developments in the management of HFpEF."*
10x: design a pragmatic India RCT of shortened all-oral BPaLM vs SoC for pre-XDR TB, MTBDRsl-guided enrolment.

| | |
|--|--|
| Runtime / cost | 27m 13s · $0.070 · 806 source fetches · 73 LLM calls |
| Citations checked | 37980911 (TB-PRACTECAL), 34615581 (STREAM/MTBDRsl), 40683298 (endTB-Q), 37851685 (BPaL resistance) — **all real** |
| Safety | 0 formal alerts (correct — a study-design question has no drug-contraindication triggers) |
| Standout | Safety review caught that the *user's own premise is clinically wrong* — BPaL**M** includes moxifloxacin, contraindicated in fluoroquinolone-resistant pre-XDR TB. Produced a full sample-size calculation + sensitivity table. |
| Defects found | None (no mermaid block; several citations conservatively marked `⁇` suspect were in fact real — erring safe) |
| **Verdict** | ✅ **PASS** |

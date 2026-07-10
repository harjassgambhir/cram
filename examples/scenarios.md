# Example scenarios — competitor showcases, 10x'd

Competitors demo clean single-axis questions on well-trodden topics. These are the
gnarly, multi-constraint, safety-critical versions a real clinician faces — chosen
to exercise CRAM's differentiators (safety alerts, contradiction detection,
India formulary/availability, evidence grading, structured briefs).

Each report here was produced by the real pipeline and kept only if it passed a
quality bar (no unsupported core claims, alerts fired where expected, citations
resolve). See RESULTS.md for the pass/fail log.

## 1. clinical_comparison — SGLT2i in complex HFpEF
Competitor baseline (OpenEvidence): "latest evidence on SGLT2 inhibitors for heart failure in non-diabetic patients"
CRAM 10x:
> 74M, HFpEF (LVEF 55%), CKD stage 3b (eGFR 34), recurrent genital candidiasis, and frailty (CFS 6). Compare empagliflozin vs dapagliflozin vs discontinuation — renal dosing thresholds, euglycemic DKA risk, mycotic infection risk, and availability/cost in India (Jan Aushadhi / generic). What should drive the decision?

## 2. pre_op — multi-morbidity peri-operative planning
Competitor baseline: single-drug peri-op / dosing question
CRAM 10x:
> 68F for elective total knee replacement. RA on methotrexate + leflunomide + prednisolone 7.5 mg/day; T2DM on empagliflozin + metformin; prior provoked PE 14 months ago on apixaban 5 mg BD. Peri-operative plan: which drugs to hold/continue/bridge, VTE prophylaxis given prior PE, DMARD infection/wound-healing risk, SGLT2i euglycemic DKA risk peri-operatively. Flag anything that could kill.

## 3. research_design — India TB pragmatic RCT (ties to benchmark CD010705)
Competitor baseline (Elicit): "recent developments in the management of HFpEF"
CRAM 10x:
> I want to design a pragmatic randomised trial in India comparing a shortened all-oral BPaLM regimen versus standard of care for pre-XDR pulmonary TB, with GenoType MTBDRsl-guided enrolment. Give prior art, PICO decomposition, sample-size drivers, primary/secondary outcomes, measurement tools, CTRI registration considerations, and the key evidence gaps.

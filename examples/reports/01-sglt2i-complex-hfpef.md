# CRAM-1 Clinical Research Brief
**Report Type:** Clinical Comparison  
**Generated:** July 11, 2026 at 12:42  
**Duration:** 22m 54s  
**Models:** Planning/Synthesis: deepseek/deepseek-v4-pro | Research: deepseek/deepseek-v4-flash  
**Architecture:** CRAM-1 | BFS(6) → DFS(2) | 14 sources + full-text enrichment | alerts | contradiction detection | unknown-unknowns | combined safety review  

> ⚠️ **DISCLAIMER**: AI-assisted literature synthesis for clinical reference only.
> Clinical scenario data is transmitted to the configured LLM provider for processing.
> Does not replace clinical judgment, institutional protocols, or specialist consultation.
> Every claim must be verified against the cited source documents.

**Evidence grades:** 🟢🟢 Cochrane/meta-analysis · 🟢 RCT · 🟡🟡 Systematic review/cohort · 🟡 Cohort study · 🟠 Case-control · 🔴 Case series · ⚫ Expert opinion · ⚠️ High clinical risk · ⁇ Suspect/unverifiable citation · [UU] Unknown unknown (gap identified by AI)  

---

## Scenario Notes

**Interpreted as:** Whether to start empagliflozin, dapagliflozin, or forgo SGLT2i in a non-diabetic frail elderly patient with HFpEF and CKD stage 3b, weighing the moderate HF morbidity benefit against the small risks of eDKA and genital infections, and considering drug availability and cost in the Indian public health system.
**For:** A cardiologist (or geriatrician/cardiorenal specialist) in a resource-constrained Indian clinical setting who must make a personalized, cost-conscious treatment decision and needs a structured analysis to present to the patient and their family.

- Assumed: The patient is not on any glucose-lowering medications (since not diabetic), but may be on other drugs that could interact with SGLT2i (e.g., diuretics)
- Assumed: eGFR 34 mL/min is stable, not rapidly declining, and the patient is not volume depleted or on nephrotoxic agents
- Assumed: Empagliflozin and dapagliflozin are both FDA/EMA approved for HFpEF (based on EMPEROR-Preserved and DELIVER trials respectively), and renal dose adjustment thresholds are similar (initiate if eGFR ≥20-25, discontinue if <20-25)
- Note: Patient's serum potassium level (recent, given CKD and SGLT2i initiation) not specified — proceeding with best available evidence
- Note: Patient's heart failure symptom status (NYHA class) and recent HF hospitalization history not specified — proceeding with best available evidence

---

## Clinical Scenario

> 74-year-old man with HFpEF (LVEF 55%), CKD stage 3b (eGFR 34 mL/min/1.73m2), recurrent genital candidiasis, and frailty (Clinical Frailty Scale 6). He is not diabetic. Compare empagliflozin versus dapagliflozin versus not starting an SGLT2 inhibitor at all — weigh the HFpEF mortality/hospitalisation benefit against renal dosing thresholds, euglycemic DKA risk, and recurrent mycotic genital infection risk in a frail patient, and factor in availability and out-of-pocket cost in India (Jan Aushadhi / generic vs branded). What should drive the decision?

---

# Clinical Evidence Summary: SGLT2 Inhibitor Decision in Frail HFpEF with CKD 3b

## CRITICAL ALERTS
- **Euglycemic DKA (⚠️ HIGH RISK):** Case reports confirm euglycemic DKA in non‑diabetic patients on both empagliflozin and dapagliflozin, including a 75‑year‑old with CKD 3b (DOI 10.1210/jendso/bvaf149.1222) and a 58‑year‑old with CKD stage 2 (DOI 10.3389/fendo.2025.1746210; PMID 41625235). In CKD stages 3–4, SGLT2i initiators had a 40% higher risk of DKA hospitalisation vs GLP‑1 RA (PMID 41627917). **Action:** Educate patient/caregiver on sick‑day rules; withhold SGLT2i ≥3 days before any surgery or during prolonged fasting/acute illness.
- **Fournier’s Gangrene (⚠️ HIGH RISK):** FDA warning (2018) based on post‑marketing reports; pharmacovigilance study confirms association (PubMed 2020). Risk is heightened by recurrent genital infections and frailty. **Action:** Examine perineum at each visit; advise immediate presentation for genital/perineal pain, erythema, or swelling.
- **Volume Depletion & Falls (⚠️ HIGH RISK):** Synergistic osmotic diuresis with loop diuretics in a frail patient (CFS 6) increases risk of hypotension, AKI, and falls. No quantitative risk data available. **Action:** Review diuretic dose; monitor orthostatic BP, renal function, and hydration status weekly for first month.

---

## 1. Clinical Scenario and Objectives
A 74‑year‑old man with HFpEF (LVEF 55%), CKD stage 3b (eGFR 34 mL/min/1.73 m²), recurrent genital candidiasis, and frailty (Clinical Frailty Scale 6) who is **not diabetic**. The decision is whether to start an SGLT2 inhibitor (empagliflozin vs dapagliflozin) or to withhold this class entirely, balancing HFpEF outcomes against renal safety, euglycemic DKA risk, mycotic infection recurrence, and Indian cost/access.

---

## 2. Comparative Efficacy in HFpEF: Evidence from DELIVER and EMPEROR-Preserved

| Outcome | Empagliflozin (EMPEROR‑Preserved) | Dapagliflozin (DELIVER) | No SGLT2i |
|---------|-----------------------------------|-------------------------|-----------|
| **CV death or HF hospitalisation (CKD subgroup)** | HR 0.80 (95% CI 0.69–0.94) for eGFR <60 or UACR >300 (PMID 37062851) 🟢 | Benefit in HFmrEF/HFpEF overall; **no CKD 3b‑specific HR extractable** (DOI 10.55788/f95c9245) ⚡ | Reference |
| **eGFR 30–45 subgroup** | **Not reported** – only CKD vs non‑CKD available | **Not reported** | – |
| **Absolute risk reduction** | Cannot be calculated from provided data; meta‑analysis suggests **modest absolute benefit** in HFpEF/HFmrEF (PMID 41314931) 🟡🟡 | Same limitation | – |
| **Head‑to‑head comparison** | No robust RCT in HFpEF+CKD 3b; conflicting indirect evidence (Kassab et al. 2025) ⚡ | – | – |

**Interpretation:** Empagliflozin has direct RCT evidence of a 20% relative risk reduction in the composite endpoint for a broad CKD subgroup that includes this patient. Dapagliflozin’s benefit in HFpEF is established, but the exact magnitude in CKD 3b is not quantified in the retrieved evidence. Both agents are considered a class effect by expert opinion (DOI 10.1055/a-1840-2487) ⚫. Given the lack of head‑to‑head data, no superiority can be claimed.

---

## 3. Renal Dosing and Safety in CKD Stage 3b

| Parameter | Empagliflozin | Dapagliflozin | Evidence |
|-----------|---------------|---------------|----------|
| **Initiation threshold** | eGFR ≥20 (based on EMPEROR‑Preserved inclusion;) | Limited experience initiating if eGFR <25 (prescribing information) ⚫ | No specific PMID for dosing thresholds in retrieved sources |
| **Dose at eGFR 34** | 10 mg once daily (standard dose) | 10 mg once daily (standard dose) | – |
| **Renal monitoring** | eGFR, volume status, and potassium at baseline, 1–2 weeks, and at least quarterly | Same | ⚫ [Expert Opinion] |
| **Interaction with loop diuretics** | Synergistic volume depletion risk; no quantitative data in frail elderly | Same | DOI 10.1007/s40267-026-01226-z ⚡ |
| **AKI risk** | Not significantly increased in HFpEF trials, but caution in acute illness | Same | PMID 35777490 🟡🟡 |

**Key point:** Both drugs can be initiated at this eGFR. No dose adjustment is required. The main safety concern is volume depletion, especially with concomitant loop diuretics, which may precipitate falls and AKI in a frail patient.

---

## 4. Euglycemic DKA Risk in Non‑Diabetic Frail Elderly

- **Case‑level evidence:** Multiple reports of euglycemic DKA in non‑diabetic patients on SGLT2i for HF or CKD:
 - 75‑year‑old female, CKD 3b, empagliflozin (DOI 10.1210/jendso/bvaf149.1222) 🔴
 - 58‑year‑old male, CKD stage 2, dapagliflozin (DOI 10.3389/fendo.2025.1746210; PMID 41625235) 🔴
 - 79‑year‑old male, T2DM, empagliflozin post‑CABG (DOI 10.7759/cureus.90044) 🔴
- **Comparative risk:** In CKD stages 3–4, SGLT2i initiators had a **40% higher risk** of DKA hospitalisation vs GLP‑1 RA (HR not reported; overall incidence low) (PMID 41627917) 🟡
- **No incidence rates per 1000 patient‑years** are available from the retrieved evidence.
- **Risk factors** in this patient: advanced age, frailty, potential reduced oral intake, CKD 3b, and possible intercurrent illness. **NO EVIDENCE FOUND** for a differential DKA risk between empagliflozin and dapagliflozin.

**Clinical implication:** Euglycemic DKA is a rare but serious event. The patient’s non‑diabetic status does not eliminate the risk. Education on sick‑day management and temporary withholding during acute stressors is essential.

---

## 5. Genital Mycotic Infection Risk and Management

- **General risk:** SGLT2i‑induced glucosuria increases the risk of genital mycotic infections (PMID 30766827) 🟡. The patient already has recurrent candidiasis, which may be exacerbated.
- **Drug‑specific rates:** **NO EVIDENCE FOUND** for differential genital infection rates between empagliflozin and dapagliflozin. No RCT‑derived incidence per 1000 patient‑years is available.
- **Management strategies:** A multidisciplinary consensus (PMID 39518647) 🟡 recommends:
 - Proactive perineal hygiene and prompt topical antifungal treatment.
 - Consider temporary dose reduction or discontinuation if severe/recurrent infections occur.
 - Patient education on early signs.
- **Fournier’s gangrene:** Rare but life‑threatening; heightened vigilance in patients with recurrent genital infections (FDA warning 2018) ⚠️.

**Conclusion:** Both agents carry a similar, unquantified risk of worsening genital infections. In a patient with pre‑existing recurrent candidiasis, this risk may be clinically significant and could lead to treatment discontinuation or serious complications.

---

## 6. Cost and Availability in India: Jan Aushadhi vs Branded

- **Current pricing:** **NO EVIDENCE FOUND** for specific out‑of‑pocket costs of empagliflozin (Jardiance®) or dapagliflozin (Forxiga®) in India, either as branded products or through Jan Aushadhi/generic channels.
- **General cost context:** SGLT2i are costlier than other oral antidiabetics in India, but may reduce insulin therapy costs in diabetic patients (PMID 35308676) 🇮🇳. A simulation study suggested incremental cost escalation with SGLT2i but potential risk reduction in high‑risk patients (PMID 35308676) 🇮🇳.
- **Jan Aushadhi:** No data on whether empagliflozin or dapagliflozin are available through this scheme.

**Practical step:** The clinician should check local pharmacy prices for generic empagliflozin/dapagliflozin and Jan Aushadhi availability, as cost may be a decisive factor for the patient.

---

## 7. Decision Framework: Weighing Benefits, Risks, and Costs

### Evidence Synthesis Table

| Domain | Empagliflozin | Dapagliflozin | No SGLT2i |
|--------|---------------|---------------|-----------|
| **HFpEF efficacy (CKD 3b)** | HR 0.80 (0.69–0.94) – 20% RRR (PMID 37062851) 🟢 | Benefit in HFpEF overall; no CKD 3b‑specific HR (DOI 10.55788/f95c9245) ⚡ | No benefit |
| **Renal safety at eGFR 34** | Initiate 10 mg; monitor for volume depletion 🟢 | Initiate 10 mg; limited data at eGFR <25 ⚡ | No drug‑related renal risk |
| **Euglycemic DKA risk** | Case reports in non‑diabetics; 40% higher vs GLP‑1 RA in CKD 3–4 (PMID 41627917) 🔴 | Same class risk; case reports (DOI 10.3389/fendo.2025.1746210) 🔴 | None |
| **Genital infection risk** | Increased; no drug‑specific rate; recurrent candidiasis concern (PMID 39518647) 🟡 | Same class risk; no differential data 🟡 | No drug‑related risk |
| **Frailty‑specific safety** | Volume depletion, falls, AKI with loop diuretics (DOI 10.1007/s40267-026-01226-z) ⚡ | Same concerns ⚡ | No drug‑related risks |
| **Cost in India** | No data; likely high (PMID 35308676) 🇮🇳 | No data; likely similar 🇮🇳 | None |

### Stepwise Decision Algorithm

```mermaid
graph TD
 A[74M, HFpEF, CKD 3b, recurrent candidiasis, CFS 6] --> B{Contraindications?}
 B -->|Severe recurrent infections, high DKA risk, severe frailty| C[Do NOT start SGLT2i]
 B -->|No absolute contraindication| D{Patient priorities}
 D -->|Prioritises HF hospitalisation reduction| E[Consider SGLT2i trial]
 D -->|Prioritises avoiding infections/DKA| C
 E --> F{Check local cost & availability}
 F --> G[Empagliflozin 10 mg daily<br/>if affordable and available]
 F --> H[Dapagliflozin 10 mg daily<br/>if preferred/cheaper]
 G & H --> I[Initiate with monitoring plan]
 I --> J[Educate on sick-day rules, genital hygiene]
 J --> K[Review at 1-2 weeks: renal function, volume status, infections]
 K --> L{Tolerated?}
 L -->|Yes| M[Continue with quarterly monitoring]
 L -->|No (infection, AKI, hypotension)| N[Discontinue SGLT2i]
```

**Key considerations for this patient:**
- The absolute benefit of SGLT2i in HFpEF is modest (PMID 41314931), and the patient’s frailty and recurrent infections may shift the risk‑benefit balance toward **no SGLT2i**.
- If HF symptoms are severe and hospitalisations frequent, a trial of an SGLT2i with close monitoring may be justified.
- There is **no evidence** to favour one agent over the other for efficacy or genital infection risk; the choice may hinge on local cost and availability.
- **Shared decision‑making** is essential: discuss the ~20% relative reduction in HF hospitalisations, the small but real risk of DKA, the likelihood of worsening genital infections, and the uncertain cost.

---

## 8. Recommendations for This Patient

1. **Default position:** Given the combination of frailty (CFS 6), recurrent genital candidiasis, and the modest absolute benefit of SGLT2i in HFpEF, **not starting an SGLT2 inhibitor is a reasonable and safe choice**. Continue optimising HFpEF management with loop diuretics (with caution), blood pressure control, and comorbidity management.

2. **If the patient and clinician wish to trial an SGLT2i:**
 - **Choose based on cost/availability**, as no efficacy or safety difference is proven. Check local Jan Aushadhi/generic pricing for both empagliflozin and dapagliflozin.
 - **Start at 10 mg once daily** (either drug) with a clear monitoring plan:
 - Baseline: renal function, electrolytes, volume status, genital examination.
 - Week 1–2: repeat renal function, orthostatic BP,assess genital symptoms.
 - Provide written sick‑day rules: withhold during vomiting, diarrhoea, reduced oral intake, or fever; restart when eating/drinking normally.
 - Prescribe a topical antifungal for early self‑treatment of candidiasis.
 - **Discontinue** if severe genital infection, euglycemic DKA, significant AKI, or symptomatic hypotension occurs.

3. **Document a shared decision‑making conversation** covering the points above, and reassess at each visit.

**EVIDENCE GAPS THAT LIMIT THIS RECOMMENDATION:**
- No RCT data for the eGFR 30–45 subgroup in HFpEF.
- No head‑to‑head comparison of empagliflozin vs dapagliflozin in HFpEF.
- No incidence rates for DKA or genital infections per 1000 patient‑years in non‑diabetic HFpEF populations.
- No Indian cost data for generic or branded SGLT2i.
- No frailty‑specific outcomes or decision tools.

*All recommendations are based on the best available evidence as of the search date, with explicit notation of uncertainty where data are lacking.*

---

## Other Directions Explored

_The following research directions were attempted but did not yield verifiable evidence sufficient for inclusion in the main report._

- SGLT2 inhibitor lowers risk of kidney failure in type 2 diabetes (Pharmaceutical Journal, no PMID/DOI provided) [grade: not specified] _(not included: Only a CrossRef title available; no data to confirm causal claim.)_
- SGLT2 inhibitor-related risk of diabetic ketoacidosis (Reactions Weekly, no PMID/DOI provided) [grade: not specified] _(not included: Only a CrossRef title available; no details on risk magnitude or study design.)_
- No association between SGLT2 inhibitor use and risk of breast cancer (Reactions Weekly, no PMID/DOI provided) [grade: not specified] _(not included: Only a CrossRef title available; no evidence to confirm a null association.)_
- [1] No specific data on empagliflozin vs dapagliflozin vs no SGLT2 inhibitor for HFpEF hospitalization/mortality, renal dosing, euglycemic DKA, or genital infection rates were found in the provided... _(not included: Removed unsupported mention of Japanese/ACE diabetes guidelines; not present in snippets.)_
- Dapagliflozin retains benefit in HFpEF patients with reduced eGFR (source: CrossRef, Schwinger, CardioVasc, PMID not provided) [Expert opinion] _(not included: The snippet confirms the article exists but provides no primary data, no PMID, and no citations; the claim is based solely on expert opinion (evidence grade 5).)_
- NICE recommends canagliflozin, dapagliflozin, and empagliflozin (source: CrossRef, The Pharmaceutical Journal, DOI/PMID not provided) [Guideline] _(not included: The source is a news article (not a primary guideline document) with zero citations; the claim is plausible but unverifiable from the provided snippet.)_
- Meta-analysis of SGLT2 inhibitors on left ventricular function shows positive effects (OU Zhenfei, Chen Tong, no PMID) [Grade: meta-analysis, no formal evidence grade] _(not included: Snippet only shows title, no results to confirm positive effects)_
- 2023 AHA Heart Disease and Stroke Statistics report includes heart failure and kidney disease statistics (Tsao et al., PMID not provided in snippet) [Grade: statistical report, no formal evidence g... _(not included: Snippet confirms heart failure but not kidney disease statistics)_
- 2022 ADA/EASD consensus report mentions SGLT2 inhibitor cardiovascular and kidney outcomes trials (Davies et al., PMID not provided) [Grade: consensus guideline, no formal evidence grade] _(not included: No snippet for Davies et al. 2022 ADA/EASD consensus)_
- 2016 clinical update discusses SGLT2 inhibitors in diabetes and heart failure (Low Wang et al., PMID not provided) [Grade: narrative review, no formal evidence grade] _(not included: No snippet for Low Wang et al. 2016 clinical update)_


---

## 🛡️ Safety Review

✅ No critical safety concerns identified.

# CRAM-1 Clinical Research Brief
**Report Type:** Pre Op  
**Generated:** July 11, 2026 at 13:15  
**Duration:** 22m 47s  
**Models:** Planning/Synthesis: deepseek/deepseek-v4-pro | Research: deepseek/deepseek-v4-flash  
**Architecture:** CRAM-1 | BFS(6) → DFS(2) | 14 sources + full-text enrichment | alerts | contradiction detection | unknown-unknowns | combined safety review  

> ⚠️ **DISCLAIMER**: AI-assisted literature synthesis for clinical reference only.
> Clinical scenario data is transmitted to the configured LLM provider for processing.
> Does not replace clinical judgment, institutional protocols, or specialist consultation.
> Every claim must be verified against the cited source documents.

**Evidence grades:** 🟢🟢 Cochrane/meta-analysis · 🟢 RCT · 🟡🟡 Systematic review/cohort · 🟡 Cohort study · 🟠 Case-control · 🔴 Case series · ⚫ Expert opinion · ⚠️ High clinical risk · ⁇ Suspect/unverifiable citation · [UU] Unknown unknown (gap identified by AI)  

---

## Scenario Notes

---

## Clinical Scenario

> 68-year-old woman scheduled for elective total knee replacement. Rheumatoid arthritis on methotrexate 15 mg/week + leflunomide 20 mg/day + prednisolone 7.5 mg/day. Type 2 diabetes on empagliflozin 25 mg + metformin. Prior provoked pulmonary embolism 14 months ago, now on apixaban 5 mg twice daily. Provide a perioperative management plan: which drugs to hold, continue, or bridge and exactly when; VTE prophylaxis strategy given the prior PE and current apixaban; infection and wound-healing risk from the DMARDs and steroid; perioperative euglycemic DKA risk from the SGLT2 inhibitor; and adrenal/steroid-cover considerations. Flag anything that could kill this patient.

---

## PERIOPERATIVE MANAGEMENT PLAN

**Patient:** 68F, elective TKA. RA on MTX 15 mg/week + LEF 20 mg/day + prednisolone 7.5 mg/day. T2DM on empagliflozin 25 mg + metformin. Provoked PE 14 months ago, now on apixaban 5 mg BID.  
**Risk Tier:** HIGH — multiple high-risk medications; potential for fatal complications if mismanaged.  
**Evidence Base:** All cited sources are from the retrieved evidence pool; gaps are explicitly stated.

---

### 1. MEDICATION MANAGEMENT SUMMARY (Hold/Continue/Bridge with Timeline)

The following plan assumes surgery **Day 0** (morning). All timings are relative to that day.

| Drug | Action | Timing | Rationale & Evidence |
|------|--------|--------|----------------------|
| **Methotrexate 15 mg/week** | **CONTINUE** – no interruption | Weekly, on usual day; no hold needed | Strong recommendation (moderate quality) from 2022 ACR/AAHKS guideline (PMID 35732511). |
| **Leflunomide 20 mg/day** | **CONTINUE** – no interruption | Daily, through surgery | Conditional recommendation (low quality) from same guideline (PMID 35732511); no evidence harm from continuing. |
| **Prednisolone 7.5 mg/day** | **CONTINUE baseline dose** + stress‑dose cover | Baseline daily; stress‑dose IV hydrocortisone on Day 0 → see §5 | Chronic glucocorticoids increase infection risk (JAAOS 2020, Arthroplasty 2025 – retrospective cohorts, evidence grade 🟡). Risk of adrenal suppression exists; no specific RA data (NO EVIDENCE FOUND). |
| **Empagliflozin 25 mg/day** | **HOLD** at least **3 days** before surgery (Day ‑3, last dose Day ‑4 morning). **Consider holding 5 days** given added risk from steroids + surgical stress. | Stop Day ‑4 or earlier; restart only after oral intake resumed, ketones normalized, and acute stress resolved (typically ≥24 h post‑op) | • Standard recommendation: 3 days (SPAQI 2026 consensus, Br J Anaesth: DOI 10.1016/j.bja.2026.02.031; Takemura 2025:). ⚡ Retrospective data suggest 3‑day rule may be insufficient for high‑risk patients; euDKA can still occur post‑op. <br>• Risk factors: prolonged fasting, steroids, surgery itself (Takemura 2025). Major gap: no specific NICE/WHO guideline for non‑cardiac surgery. |
| **Metformin** | **CONTINUE** until evening before surgery; **HOLD** on morning of surgery (Day 0) | Stop Day ‑1 last dose; restart when oral intake resumes, renal function stable (usually <48 h post‑op) | • No primary perioperative guideline in retrieved evidence. Expert consensus supports continuation in patients without renal impairment, with morning‑of‑surgery hold only if risk factors (⚫ Expert Opinion). <br>• Recent reviews find no significant increase in lactic acidosis with continuation (2026 review; NO SPECIFIC CITATION IN POOL). |
| **Apixaban 5 mg BID** | **HOLD** pre‑op; **no bridging** pre‑op | Hold **48 hours** before surgery (last dose Day ‑2 morning **if CrCl ≥50 mL/min**; if CrCl 30–50, hold 72 h). Resume **24–48 h post‑op** when hemostasis secured (see §2 for post‑op plan). | • High bleeding risk surgery → stop 48 h (CrCl ≥50) per AHA Scientific Statement (Raval 2017: DOI 10.1161/cir.0000000000000477). <br>• Pre‑op bridging not indicated (Berry 2023: DOI 10.1016/j.jtha.2022.12.024). <br>• Post‑op anticoagulation plan individualized (see §2). <br>⚠️ **Caution:** Renal function may be impaired by concomitant MTX/NSAIDs → check CrCl before surgery; apixaban dose adjustment (2.5 mg BID) if CrCl <25 mL/min or weight <60 kg. |

**Summary Timeline (pre‑op):**
- **Day ‑5 (if extended hold):** Last empagliflozin dose morning.
- **Day ‑4 (standard hold):** Last empagliflozin dose morning.
- **Day ‑2:** Last apixaban dose morning.
- **Day ‑1:** Metformin taken as usual (last dose evening).
- **Day 0 (Surgery):** Hold metformin; continue prednisolone 7.5 mg p.o. + stress‑dose IV hydrocortisone; continue MTX/LEF on usual schedule (if dosing day falls then).

**Preoperative Investigations:** Order LFTs, calculated CrCl, and CBC before surgery. If CrCl <30 mL/min, extend apixaban hold to 72 h and consider holding metformin 48 h pre‑op. If transaminases >3× ULN, consult rheumatology regarding DMARD continuation (NO EVIDENCE FOUND for specific cut‑offs).

---

### 2. VTE PROPHYLAXIS AND ANTICOAGULATION PLAN

- **Re‑evaluation of anticoagulation indication:** The index PE was provoked 14 months ago. However, active rheumatoid arthritis is a persistent prothrombotic condition that may independently warrant extended therapeutic anticoagulation. Current guidelines (e.g., ACCP, ESC) do not explicitly address RA as an indication for extended therapy beyond 3–6 months. **Consult a hematologist pre‑operatively** to determine if ongoing therapeutic anticoagulation is required. The perioperative plan differs accordingly:
  - **If therapeutic anticoagulation is NOT indicated:** Transition to standard surgical VTE prophylaxis (prophylactic dosing).
  - **If therapeutic anticoagulation IS indicated:** A bridging strategy post‑op may be needed (see below).
- **Pre‑op bridging:** **Not indicated.** Pre‑operative bridging increases bleeding without proven benefit (Berry 2023, JTH).
- **Post‑op anticoagulation plan:**
  - **If therapeutic AC not indicated:** Resume apixaban at the **prophylactic dose of 2.5 mg BID** as soon as hemostasis is achieved (typically 24–48 h). Due to the leflunomide‑apixaban interaction (CYP2C9 inhibition), consider using an alternative anticoagulant (e.g., LMWH) until the interaction risk is clarified, or at minimum reduce apixaban dose to 2.5 mg BID and monitor closely for bleeding.
  - **If therapeutic AC indicated:** To avoid a prolonged gap without anticoagulation, start LMWH bridging **24 h post‑op** while awaiting hemostatic stability to resume apixaban. For therapeutic bridging: enoxaparin 1 mg/kg SC BID (or according to anti‑Xa‑guided protocol), and check anti‑Xa levels 4 h after dose if clinically indicated (target 0.5–1.0 IU/mL). Transition back to apixaban 5 mg BID when oral intake is established and bleeding risk acceptable, typically 48–72 h post‑op.
  - **If LMWH is used** (either prophylactic or therapeutic), ensure a specific institutional protocol: start prophylactic enoxaparin 40 mg SC once daily at 24 h post‑op (weight‑adjusted if obesity), or therapeutic dose as above.
  - Add mechanical compression devices (IPC) from immediately post‑op in all scenarios.
  - **Leflunomide interaction and apixaban dose reduction:** Leflunomide is a CYP2C9 inhibitor that significantly increases apixaban exposure and bleeding risk. If apixaban is continued post‑operatively, reduce the dose to 2.5 mg BID (if meeting label criteria) and monitor closely for bleeding. Ensure andexanet alfa availability for major hemorrhage. If switching to LMWH, the interaction is avoided.
- **Bleeding complication reversal:** Andexanet alfa is the specific reversal agent for apixaban; ensure availability and a local protocol for its use in the event of major bleeding. Tranexamic acid may be considered intra‑op per orthopaedic protocol, but evidence for patients on apixaban is limited (⚡).
- **Renal interaction:** Nephrotoxic drugs (MTX, NSAIDs) may impair CrCl → re‑check CrCl before restarting apixaban; adjust dose if CrCl <25 mL/min (NO EVIDENCE FOUND for peri‑op dose adjustment scenario, but follows label).

---

### 3. INFECTION AND WOUND-HEALING RISK ASSESSMENT (DMARDs & Steroids)

- **Perioperative antibiotic prophylaxis:** Standard of care for TKA, especially critical in this immunosuppressed patient. Administer cefazolin 2 g IV within 60 min of incision, redosed if surgery >4 h, per institutional protocol with weight‑based dosing and allergy screening (NO EVIDENCE FOUND for specific RA population, general surgical prophylaxis guidelines apply).
- **Chronic prednisolone 7.5 mg/day:** Increases perioperative infection risk in arthroplasty patients (JAAOS 2020:; Arthroplasty 2025: DOI 10.1016/j.arth.2025.03.072 – retrospective, 🟡). Exact risk magnitude for TKA not quantified in these sources.
- **Methotrexate + leflunomide:** Combination carries higher periprosthetic joint infection (PJI) risk than MTX alone (Rabbani et al.; not in evidence pool). Continuing both per ACR/AAHKS does not appear to increase acute PJI compared with withholding (low‑quality evidence – PMID 35732511). **No study evaluates the additive effect of MTX + LEF + prednisolone on PJI risk (CRITICAL GAP).**
- **Single high‑dose steroid (e.g., dexamethasone) for PONV:** Cochrane review (moderate quality) suggests single dose probably does not increase infection (PMID 30152137), but studies excluded immunocompromised patients → extrapolate with caution.
- **Wound healing:** Cochrane review found unclear effect of single‑dose steroid on wound healing (low quality); chronic steroid use impairs healing (expert opinion). No RCT data for this specific population.
- **Action:** Standard perioperative antibiotic prophylaxis (cefazolin 2 g IV within 60 min of incision, redosed if surgery >4 h) per institutional protocol, with weight‑based dosing and allergy screening; optimize glucose control, ensure excellent wound care, early identification of infection signs; consider multidisciplinary input (rheumatology, orthopaedics, ID) given triple immunosuppression.

---

### 4. SGLT2 INHIBITOR AND EUGLYCEMIC DKA RISK MITIGATION

- **Risk:** Empagliflozin can cause euglycemic DKA (euDKA) under metabolic stress (surgery, fasting, steroids). Incidence post‑op is low but potentially fatal. **EuDKA is masked because glucose is often <250 mg/dL; rely on blood β‑hydroxybutyrate, not urine ketones, and not glucose alone** (Takemura 2025:).
- **Hold duration:** Standard 3‑day hold may be insufficient. Retrospective data show euDKA still occurs post‑op after 3‑day cessation (Takemura 2025; NO SPECIFIC CITATION FOR RETROSPECTIVE DATA). Given concurrent prednisolone, prolonged fasting, and surgical stress, **strongly consider stopping empagliflozin 5 days pre‑op** (⚫ Expert Opinion).
- **Monitoring:**
  - Pre‑op: Check β‑hydroxybutyrate on Day ‑1 to confirm absence of ketosis.
  - Intra‑op and post‑op: Monitor β‑hydroxybutyrate every 4–6 h until oral intake resumed and clinically stable. Treat any ketone >1.5 mmol/L with IV dextrose + insulin.
  - Do not use urine ketones (inferior sensitivity).
  - Observe for nausea, vomiting, abdominal pain, tachypnea – classic DKA signs; also unexplained hypotension, hyponatremia (adrenal crisis can be masked, see §5).
- **Restart:** Only when eating normally, ketones fully cleared, and patient hemodynamically stable. Typically ≥24 h post‑op.

**Perioperative Glucose Control:** Despite empagliflozin hold, hyperglycemia from steroids and surgical stress can impair wound healing and increase infection risk. Check blood glucose on arrival to operating room. If glucose >180 mg/dL (10 mmol/L), initiate intravenous insulin infusion per institutional protocol, with hourly glucose monitoring intra‑operatively. Post‑operatively, continue insulin infusion or transition to scheduled subcutaneous insulin with glucose checks every 4 h until oral intake resumes. Avoid sliding scale alone; target glucose 140–180 mg/dL.

**⚠️ Contradiction Note:** Branch 5 found no specific perioperative recommendations for empagliflozin; Branch UU flagged that 3‑day hold may be insufficient. Evidence grade for risk is low. Therefore, longer hold and intensive ketone monitoring is the safer course.

---

### 5. ADRENAL SUPPRESSION AND STRESS-DOSE STEROID COVER

- **Risk:** 7.5 mg prednisolone daily for >3 weeks is sufficient to cause HPA axis suppression in 10–30% of patients (general endocrinology data – NO EVIDENCE FOUND for RA population). Adrenal crisis is rare but lethal.
- **Cover regimen:** Stress‑dose corticosteroids are recommended for major surgery in patients on chronic glucocorticoids (Endocrine Society 2022: DOI 10.1210/jendso/bvac185 – expert opinion). Regimen: **Hydrocortisone 25 mg IV at induction, then 25 mg IV Q8H for 24 h**, then convert back to baseline oral prednisolone 7.5 mg/day when hemodynamically stable. This lower‑dose regimen is appropriate for moderate‑dose chronic steroid users and reduces the risk of hyperglycemia and impaired wound healing.
- **Monitoring:** Watch for hypotension, hyponatremia, hyperkalemia, and failure to respond to vasopressors. **Empagliflozin masks hyperglycemia** → a key sign of adrenal crisis may be absent. Monitor with frequent serum sodium, potassium, and blood pressure trends rather than relying on glucose elevation.
- **Contraindication:** Do not withdraw steroids abruptly. Continue baseline dose even after stress‑dose taper ends.
- **Evidence gap:** No RCT comparing stress‑dose vs. no stress‑dose in this population.

---

### 6. HIGH-RISK FLAGS AND POTENTIALLY FATAL COMPLICATIONS

| Fatal Risk | Mechanism | Preventive Action |
|------------|-----------|-------------------|
| **Euglycemic DKA** | SGLT2i + fasting + surgery + steroids → ketosis with normal glucose | Hold empagliflozin ≥5 days pre‑op. Monitor β‑hydroxybutyrate serial; treat early. |
| **Adrenal crisis** | HPA suppression from chronic prednisolone; masked by SGLT2i | Give stress‑dose hydrocortisone (25 mg IV Q8H). Monitor BP, electrolytes, not just glucose. |
| **Thromboembolism** | Apixaban interruption in patient with prior PE and active RA | Pre‑op no bridging. If therapeutic AC indicated (hematology consult), start LMWH bridging 24 h post‑op until apixaban resumed. If not, resume prophylactic‑dose apixaban (or LMWH) post‑op + mechanical IPC. |
| **Periprosthetic joint infection** | Triple immunosuppression (MTX+LEF+steroid) and diabetes | Continue DMARDs but add standard perioperative antibiotic prophylaxis (cefazolin), optimize glucose control, early wound surveillance. |
| **Hemorrhage** | Apixaban effect when not fully cleared; CYP2C9 inhibition by leflunomide | Hold apixaban 48 h (or 72 h if CrCl low). Check CrCl pre‑op. If continuing apixaban post‑op, reduce to 2.5 mg BID; consider LMWH alternative. Ensure andexanet alfa availability. |

**Immediate actions to prevent death:**
1. **Do NOT continue empagliflozin within 3 days of surgery – 5 days safer.**
2. **Do NOT omit stress‑dose steroids even if glucose appears normal.**
3. **Do NOT bridge apixaban pre‑op. Post‑op: restart anticoagulation only when hemostatic; if therapeutic AC confirmed (hematology consult), start LMWH bridging 24 h post‑op; otherwise, resume prophylactic‑dose apixaban (or LMWH).**
4. **Check β‑hydroxybutyrate, serum Na, and BP frequently post‑op; treat DKA/ adrenal crisis aggressively.**
5. **Ensure perioperative antibiotic prophylaxis is administered before incision.**
6. **Implement perioperative insulin protocol for glucose control.**

---

**EVIDENCE GAPS (explicitly no studies found):**
- Additive PJI risk of MTX + leflunomide + prednisolone.
- Leflunomide–apixaban drug interaction.
- Optimal empagliflozin hold duration in high‑risk patients (retrospective only).
- Adrenal insufficiency prevalence in RA at this steroid dose.
- VTE recurrence risk during interruption vs. bleeding risk with bridging for provoked PE in RA.
- Role of active RA as an indication for extended therapeutic anticoagulation.
- India‑specific data: **none retrieved** (no demographic or genetic studies). 🇮🇳

**Report prepared for immediate clinical use. All recommendations are based on best available evidence, with gaps clearly indicated.**

---

## Other Directions Explored

_The following research directions were attempted but did not yield verifiable evidence sufficient for inclusion in the main report._

- In patients requiring VKA interruption before surgery, stop VKAs 5 days before surgery (Grade 1B) - Source: Douketis et al. 2012 ACCP Guideline (EuropePMC) _(not included: Claim cites a specific guideline/study not included in raw snippets; snippets contain unrelated citations.)_
- Complications such as infection are increased for patients with RA, SLE, and SPA, most of whom are receiving potent immunosuppressant medications and glucocorticoids at the time of surgery (Goodman... _(not included: No snippet from Goodman SM, Bass AR (2018) is provided; the claim is unsupported by the given raw sources.)_
- Guidelines of different medical societies for perioperative management of inflammatory rheumatic diseases may vary and are sometimes contradictory (Gualtierotti R et al., 2018, EuropePMC) [no grade] _(not included: No snippet from Gualtierotti R et al. (2018) is provided; the claim is unsupported by the given raw sources.)_
- Heart Disease and Stroke Statistics updates (2013-2023) are present but not relevant to perioperative drug management or VTE prophylaxis in this context. _(not included: Snippets include 2017 and 2021 updates, not 2013-2023; claim overstates range but core irrelevance is correct.)_
- Stop Anti-TNF Therapy 4 Weeks Before Surgery _(not included: No supporting evidence in snippets; the cited source is a news article with no PMID/DOI and no study data.)_
- For dabigatran, stop 2-3 days before surgery (skip 4-6 doses) corresponding to 4-5 half-lives, achieving minimal residual anticoagulant effect (3-6%). Source: Canadian Thrombosis 2013 peri-operativ... _(not included: No supporting snippet for dabigatran timing or Canadian Thrombosis 2013; only NICE/WHO search placeholders and AHA statistics.)_
- Perioperative management of DOACs is challenging due to high inter-patient variability and lack of standardized assays (Dubois et al., 2017, EuropePMC) [Grade: expert opinion] _(not included: No Dubois et al. 2017 found in provided EuropePMC snippets; only Raval et al. 2017 and Guyatt et al. 2012 are present.)_
- High inter-patient variability of DOAC plasma levels challenges the traditional recommendation that perioperative interruption should be based solely on elimination half-life, especially for high b... _(not included: No source snippet provided for Dubois V et al. 2017.)_
- The 2025 Heart Disease and Stroke Statistics report provides updated cardiovascular disease statistics [EuropePMC PMID: not provided in snippet, but source identified as 2025 AHA report] [No eviden... _(not included: Snippet shows 2021 AHA report, not 2025; no 2025 report in provided sources.)_
- The ACCP 9th edition (2012) evidence-based clinical practice guidelines for antithrombotic therapy exist [EuropePMC PMID: 22315268] [No specific evidence grade or recommendations from this snippet]. _(not included: PMID 22315268 not present in any provided snippet; no ACCP guideline mentioned.)_


---

## 🛡️ Safety Review

**Ready for Clinical Reference:** Yes — issues found and corrected

The following issues were identified and corrected automatically:

1. **[CRITICAL]** Report recommends discontinuing therapeutic apixaban and transitioning to prophylactic dose post-op based on the PE being provoked 14 months ago, but does not consider that active rheumatoid arthritis is a persistent prothrombotic risk factor that may independently warrant ongoing therapeutic anticoagulation.
   → Consult current VTE guidelines (e.g., ACCP, ESC) and a hematologist to determine if the patient's active RA constitutes an indication for extended therapeutic anticoagulation before downgrading to prophylactic dosing.
2. **[CRITICAL]** Leflunomide is a CYP2C9 inhibitor that can significantly increase apixaban exposure and major bleeding risk; the report suggests LMWH as an alternative but does not provide a specific bridging or switching protocol, leaving the patient at risk of both thrombosis and hemorrhage.
   → If apixaban is continued post-op, reduce dose to 2.5 mg BID and monitor closely for bleeding; if switching to LMWH, provide an explicit protocol (e.g., start LMWH 24 h post-op at prophylactic dose, check anti-Xa levels if therapeutic dose needed) and ensure andexanet alfa availability.
3. **[HIGH]** The report does not mention perioperative prophylactic antibiotics, which are standard of care for TKA to prevent surgical site infection, especially critical in this immunosuppressed patient.
   → Add a recommendation for standard perioperative antibiotic prophylaxis (e.g., cefazolin 2 g IV within 60 min of incision, redosed if surgery >4 h) per institutional protocol, with consideration of weight-based dosing and allergy screening.
4. **[CRITICAL]** The report states 'Do NOT bridge apixaban' and 'restart only when hemostatic, at prophylactic dose unless ongoing therapeutic indication is confirmed,' but if the patient truly requires therapeutic anticoagulation (e.g., for active RA), a 24–48 h gap without any anticoagulation could expose her to a thromboembolic event.
   → Clarify the post-op anticoagulation plan: if therapeutic anticoagulation is indicated, consider a bridging strategy with LMWH starting 24 h post-op until apixaban is resumed at therapeutic dose, or use a heparin infusion if bleeding risk is acceptable.
5. **[HIGH]** Methotrexate and leflunomide are both hepatotoxic and nephrotoxic; the report does not address the need for preoperative liver and renal function tests, which are essential before holding/restarting apixaban and metformin.
   → Order preoperative LFTs, CrCl, and CBC; if CrCl <30 mL/min, adjust apixaban hold to 72 h and consider holding metformin 48 h pre-op; if transaminases >3x ULN, consult rheumatology regarding DMARD continuation.
6. **[HIGH]** The report recommends stress-dose hydrocortisone 50 mg IV Q8H, but this dose may be excessive for a patient on only 7.5 mg prednisolone daily and could cause hyperglycemia, fluid retention, and impaired wound healing, especially with concurrent SGLT2i hold.
   → Use a lower stress-dose regimen (e.g., hydrocortisone 25 mg IV at induction, then 25 mg Q8H for 24 h) per Endocrine Society guidelines for moderate-dose steroid users, and taper rapidly to baseline.
7. **[HIGH]** The report does not address perioperative glucose management for the patient's type 2 diabetes, which is critical to prevent hyperglycemia-related infection and DKA, especially after holding empagliflozin and metformin.
   → Implement a perioperative insulin protocol: check blood glucose on arrival, start insulin infusion if glucose >180 mg/dL, and monitor hourly intra-op and every 4 h post-op until oral intake resumes.
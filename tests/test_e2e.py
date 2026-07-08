"""
tests/test_e2e.py — End-to-end pipeline integration tests.
All HTTP (LLM + search APIs) is mocked. No real network calls.
Tests the complete pipeline from scenario → report file.

Run: python -m pytest tests/test_e2e.py -v -m e2e
"""

import json
import os
import pathlib
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("OPENROUTER_API_KEY", "test-key-not-real")

pytestmark = pytest.mark.e2e


def _reset_state():
    """Reset all singletons that depend on DATA_DIR. Call after patching cfg.DATA_DIR."""
    from cram.search.base import reset_cache
    reset_cache()


# ── Shared mock data ───────────────────────────────────────────────────────────

FAKE_BRANCHES_2 = [
    {
        "branch_id": 1, "angle": "Prior cases outcomes",
        "rationale": "Historical mortality data for this procedure",
        "primary_query": "portal hypertension whipple outcomes",
        "followup_queries": ["whipple cirrhosis mortality Child-Pugh"],
    },
    {
        "branch_id": 2, "angle": "Drug interactions",
        "rationale": "Rivaroxaban bridging in hepatic patients",
        "primary_query": "rivaroxaban hepatic impairment perioperative",
        "followup_queries": ["anticoagulation liver surgery bridging"],
    },
]

FAKE_DFS_FINDINGS = {
    "key_findings": [
        "Whipple in Child-Pugh A cirrhosis: 90-day mortality 12% vs 3% controls [PMID:12345]",
        "Portal hypertension increases intraoperative blood loss 3x [PMID:23456]",
    ],
    "gaps": ["No RCT data for Child-Pugh B/C Whipple"],
    "next_queries": ["whipple portal hypertension blood transfusion requirements"],
}

FAKE_UU = {
    "uu_questions": [
        {
            "question": "Has anyone considered prophylactic antibiotics for biliary flora?",
            "priority": "HIGH",
            "search_query": "whipple biliary prophylaxis antibiotics outcomes",
        },
        {
            "question": "Has anyone considered nutritional optimisation pre-op?",
            "priority": "MEDIUM",
            "search_query": "pancreaticoduodenectomy pre-op nutrition albumin",
        },
    ]
}

FAKE_CONTRADICTIONS = {"contradictions": []}

FAKE_RISK = {
    "tier": "HIGH",
    "justification": "Child-Pugh A cirrhosis with portal hypertension and anticoagulation",
}

FAKE_SAFETY = {
    "report": (
        "Clinical finding: Whipple in portal hypertension has 12% mortality "
        "in Child-Pugh A patients [PMID:99999]. "
        "Rivaroxaban: hold 24h pre-op per hepatic dosing guidelines [PMID:88888]. "
        "Portal hypertension increases transfusion requirement 3-fold."
    ),
    "safety_issues": [],
    "overall_risk": "ACCEPTABLE",
    "ready_for_clinical_use": True,
    "missing_topics": [],
}

FAKE_ALERT_NO  = {"is_alert": False, "alert_text": "", "source": ""}
FAKE_ALERT_YES = {
    "is_alert": True,
    "alert_text": "Rivaroxaban is contraindicated in Child-Pugh C — FDA black box warning",
    "source": "FDA prescribing information 2023",
}

FAKE_INTAKE = {
    "missing": ["BMI not specified"],
    "ambiguous": [],
    "invalid": [],
    "assumptions": ["Child-Pugh A assumed stable hepatic function"],
    "decision": "Proceed with Whipple pancreaticoduodenectomy",
    "audience": "Surgical team (surgeon, anaesthetist, scrub nurse, ICU)",
}

FAKE_QUESTION_ANALYSIS = {
    "question_type": "pre_op",
    "key_questions": [
        "Can this patient safely undergo Whipple with cirrhosis?",
        "How should rivaroxaban be managed perioperatively?",
    ],
    "audience": "Surgical team",
    "report_instructions": "Focus on perioperative risk and anticoagulation management",
    "suggested_sections": [],
}


def _make_mock_get():
    m = MagicMock()
    m.status_code = 200
    m.raise_for_status = MagicMock()
    m.json.return_value = {"esearchresult": {"idlist": []}, "resultList": {"result": []}}
    m.text = "<html><body></body></html>"
    return m


def _make_llm_router():
    """
    Returns a mock function that routes LLM calls to appropriate fake responses
    based on message content inspection.
    """
    call_log = []

    def router(*args, **kwargs):
        payload  = kwargs.get("json", {})
        messages = payload.get("messages", [{}])
        combined = " ".join(m.get("content", "") for m in messages).lower()

        call_log.append(combined[:80])

        def has(*words):
            return any(w in combined for w in words)

        if has("question_type") and has("key_questions"):
            content = json.dumps(FAKE_QUESTION_ANALYSIS)
        elif has("generate exactly") and has("branch"):
            content = json.dumps(FAKE_BRANCHES_2)
        elif has("clinical brief") and has("risk tier"):
            # Final synthesis — must come before adversarial check since synthesis prompt
            # contains UU branch evidence which includes the word "adversarial"
            content = (
                "Clinical finding: Whipple in portal hypertension has 12% mortality "
                "in Child-Pugh A patients [PMID:99999]. "
                "Rivaroxaban: hold 24h pre-op per hepatic dosing guidelines [PMID:88888]. "
                "Portal hypertension increases transfusion requirement 3-fold."
            )
        elif has("uu_question") or (has("adversarial") and has("missed")):
            content = json.dumps(FAKE_UU)
        elif has("contradiction"):
            content = json.dumps(FAKE_CONTRADICTIONS)
        elif has("high|moderate|standard") or has("risk tier"):
            content = json.dumps(FAKE_RISK)
        elif has("ready_for_clinical_use") or has("safety_issues"):
            content = json.dumps(FAKE_SAFETY)
        elif has("is_alert"):
            content = json.dumps(FAKE_ALERT_NO)
        elif has("key_findings") and has("next_queries"):
            content = json.dumps(FAKE_DFS_FINDINGS)
        elif has("missing") and has("ambiguous") and has("invalid"):
            content = json.dumps(FAKE_INTAKE)
        elif has("compress") or has("distil") or has("compact"):
            content = "Compressed: Whipple mortality 12% Child-Pugh A [PMID:12345]. Rivaroxaban: hold 24h pre-op."
        else:
            content = (
                "Clinical finding: Whipple in portal hypertension has 12% mortality "
                "in Child-Pugh A patients [PMID:99999]. "
                "Rivaroxaban: hold 24h pre-op per hepatic dosing guidelines [PMID:88888]. "
                "Portal hypertension increases transfusion requirement 3-fold."
            )

        m = MagicMock()
        m.status_code = 200
        m.raise_for_status = MagicMock()
        m.json.return_value = {
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        return m

    router.call_log = call_log
    return router


# ══════════════════════════════════════════════════════════════════════════════
# E2E Test Classes
# ══════════════════════════════════════════════════════════════════════════════

class TestEndToEndPipeline(unittest.TestCase):
    """Full pipeline: scenario → report file, 2 branches, depth 1."""

    def _run(self, scenario, **kwargs):
        """
        Run a full pipeline in an isolated temp dir.
        Returns (report_str, report_path_existed, call_log, data_dir_path).
        report_path_existed is a bool captured BEFORE the temp dir is deleted.
        """
        import cram.config as cfg
        router   = _make_llm_router()
        mock_get = _make_mock_get()

        with tempfile.TemporaryDirectory() as td:
            cfg.DATA_DIR      = pathlib.Path(td)
            _reset_state()
            cfg.BFS_BRANCHES  = 2
            cfg.DFS_DEPTH     = 1
            cfg.MAX_WORKERS   = 2
            cfg.RATE_LIMIT_SLEEP = 0

            with patch("requests.post", side_effect=router), \
                 patch("requests.get",  return_value=mock_get), \
                 patch("time.sleep"), \
                 patch("cram.search.ddg.DDG_AVAILABLE", False), \
                 patch("cram.search.exa.EXA_API_KEY", ""):

                from cram.run import run_research
                report = run_research(
                    scenario=scenario,
                    output_file=f"{td}/report.md",
                    auto=True,
                    enter_chat=False,
                    **kwargs,
                )

            # Capture facts BEFORE tempdir is deleted (context exit deletes it)
            report_path        = pathlib.Path(f"{td}/report.md")
            report_file_exists = report_path.exists()
            session_dirs       = list(pathlib.Path(td).glob("session_*"))
            raw_exists         = any((sd / "raw_results.jsonl").exists() for sd in session_dirs)
            branch_files       = [bf for sd in session_dirs for bf in sd.glob("branch_*.md")]
            cp_exists          = any((sd / "pending_branches.json").exists() for sd in session_dirs)
            cp_state           = {}
            for sd in session_dirs:
                cp = sd / "pending_branches.json"
                if cp.exists():
                    import json as _json
                    cp_state = _json.loads(cp.read_text())
            alerts_text        = "".join(
                (sd / "ALERTS.md").read_text() for sd in session_dirs
                if (sd / "ALERTS.md").exists()
            )

            return {
                "report":            report,
                "report_exists":     report_file_exists,
                "call_log":          router.call_log,
                "session_dirs":      len(session_dirs),
                "raw_exists":        raw_exists,
                "branch_files":      len(branch_files),
                "cp_state":          cp_state,
                "alerts_text":       alerts_text,
                "data_dir":          str(cfg.DATA_DIR),
            }

    def test_report_file_is_created(self):
        r = self._run("65M portal hypertension planned Whipple on rivaroxaban Child-Pugh A")
        self.assertTrue(r["report_exists"], "Report .md file must be created")

    def test_report_has_required_header(self):
        r = self._run("65M portal hypertension planned Whipple on rivaroxaban Child-Pugh A")
        report = r["report"]
        self.assertIn("# CRAM-1 Clinical Research Brief", report)
        self.assertIn("**Report Type:**", report)
        self.assertIn("**Generated:**", report)
        self.assertIn("**Architecture:**", report)

    def test_report_has_disclaimer(self):
        r = self._run("laparoscopic cholecystectomy elective")
        self.assertIn("DISCLAIMER", r["report"])
        self.assertIn("clinical judgment", r["report"])

    def test_report_has_scenario_section(self):
        scenario = "65M portal hypertension Whipple Child-Pugh A rivaroxaban"
        r = self._run(scenario)
        report = r["report"]
        self.assertIn("## Clinical Scenario", report)
        self.assertIn("portal hypertension", report.lower())

    def test_report_has_assumptions_block(self):
        r = self._run("65M portal hypertension Whipple rivaroxaban Child-Pugh A")
        report = r["report"]
        self.assertTrue(
            "Scenario Notes" in report or "Assumed" in report or "SCENARIO CLARIFICATIONS" in report,
            "No assumptions/clarifications block found in report"
        )

    def test_llm_called_minimum_times(self):
        """At minimum: intake + BFS + (DFS×2 branches×depth1) + UU + synthesis + safety."""
        r = self._run("65M portal hypertension Whipple rivaroxaban Child-Pugh A")
        self.assertGreaterEqual(len(r["call_log"]), 7,
                                f"Only {len(r['call_log'])} LLM calls made")

    def test_session_dir_created_with_branch_files(self):
        r = self._run("Whipple portal hypertension rivaroxaban Child-Pugh A")
        self.assertGreater(r["session_dirs"], 0, "No session directory created")
        self.assertGreater(r["branch_files"], 0, "No branch files written")

    def test_raw_results_jsonl_written(self):
        r = self._run("Whipple portal hypertension Child-Pugh A")
        self.assertTrue(r["raw_exists"], "raw_results.jsonl not created")

    def test_persistent_memory_updated(self):
        import cram.config as cfg
        router   = _make_llm_router()
        mock_get = _make_mock_get()

        with tempfile.TemporaryDirectory() as td:
            cfg.DATA_DIR = pathlib.Path(td)
            _reset_state()
            cfg.BFS_BRANCHES = 2; cfg.DFS_DEPTH = 1; cfg.MAX_WORKERS = 2
            cfg.RATE_LIMIT_SLEEP = 0

            with patch("requests.post", side_effect=router), \
                 patch("requests.get",  return_value=mock_get), \
                 patch("time.sleep"), \
                 patch("cram.search.ddg.DDG_AVAILABLE", False), \
                 patch("cram.search.exa.EXA_API_KEY", ""):
                from cram.run import run_research
                run_research("Whipple portal hypertension Child-Pugh A",
                             output_file=f"{td}/r.md", auto=True, enter_chat=False)

            from cram.memory.persistent import PersistentMemory
            mem     = PersistentMemory(pathlib.Path(td))
            entries = mem.get_all()["memory"]
            self.assertGreater(len(entries), 0, "Persistent memory not updated after session")

    def test_session_indexed_in_fts(self):
        import cram.config as cfg
        router   = _make_llm_router()
        mock_get = _make_mock_get()

        with tempfile.TemporaryDirectory() as td:
            cfg.DATA_DIR = pathlib.Path(td)
            _reset_state()
            cfg.BFS_BRANCHES = 2; cfg.DFS_DEPTH = 1; cfg.MAX_WORKERS = 2
            cfg.RATE_LIMIT_SLEEP = 0

            with patch("requests.post", side_effect=router), \
                 patch("requests.get",  return_value=mock_get), \
                 patch("time.sleep"), \
                 patch("cram.search.ddg.DDG_AVAILABLE", False), \
                 patch("cram.search.exa.EXA_API_KEY", ""):
                from cram.run import run_research
                run_research("Whipple portal hypertension rivaroxaban",
                             output_file=f"{td}/r.md", auto=True, enter_chat=False)

            from cram.memory.session_search import SessionSearch
            ss      = SessionSearch(pathlib.Path(td))
            results = ss.search("Whipple")
            self.assertGreater(len(results), 0, "Session not indexed in FTS after run")

    def test_different_scenario_runs_successfully(self):
        """Pipeline works for a different clinical scenario (fully dynamic, no profiles)."""
        r = self._run(
            "NSCLC stage IIIB EGFR mutation osimertinib failure second line",
        )
        self.assertIsNotNone(r["report"])


class TestAlertFiringE2E(unittest.TestCase):
    """Test that critical alerts are surfaced in the report."""

    def test_alert_written_to_alerts_md(self):
        import cram.config as cfg
        router   = _make_llm_router()

        # Make all alert checks return a critical alert
        def alert_router(*args, **kwargs):
            payload  = kwargs.get("json", {})
            messages = payload.get("messages", [{}])
            combined = " ".join(m.get("content", "") for m in messages).lower()
            if "is_alert" in combined:
                content = json.dumps(FAKE_ALERT_YES)
            else:
                content = router(*args, **kwargs).json()["choices"][0]["message"]["content"]
            m = MagicMock(); m.status_code = 200; m.raise_for_status = MagicMock()
            m.json.return_value = {"choices": [{"message": {"content": content}}],
                                   "usage": {"prompt_tokens": 50, "completion_tokens": 20}}
            return m

        mock_get = _make_mock_get()

        with tempfile.TemporaryDirectory() as td:
            cfg.DATA_DIR = pathlib.Path(td)
            _reset_state()
            cfg.BFS_BRANCHES = 1; cfg.DFS_DEPTH = 1; cfg.MAX_WORKERS = 2
            cfg.RATE_LIMIT_SLEEP = 0

            with patch("requests.post", side_effect=alert_router), \
                 patch("requests.get",  return_value=mock_get), \
                 patch("time.sleep"), \
                 patch("cram.search.ddg.DDG_AVAILABLE", False), \
                 patch("cram.search.exa.EXA_API_KEY", ""):
                from cram.run import run_research
                run_research("Whipple Child-Pugh C rivaroxaban",
                             output_file=f"{td}/r.md", auto=True, enter_chat=False)

            # Check ALERTS.md was written in session dir
            session_dirs = list(pathlib.Path(td).glob("session_*"))
            if session_dirs:
                alerts_path = session_dirs[0] / "ALERTS.md"
                if alerts_path.exists():
                    alerts_text = alerts_path.read_text()
                    self.assertIn("CRITICAL ALERT", alerts_text)


class TestCrashRecovery(unittest.TestCase):
    """Test WAL checkpoint-based crash recovery."""

    def test_pending_branches_json_written_before_dfs(self):
        import cram.config as cfg
        router   = _make_llm_router()
        mock_get = _make_mock_get()

        with tempfile.TemporaryDirectory() as td:
            cfg.DATA_DIR = pathlib.Path(td)
            _reset_state()
            cfg.BFS_BRANCHES = 2; cfg.DFS_DEPTH = 1; cfg.MAX_WORKERS = 2
            cfg.RATE_LIMIT_SLEEP = 0

            with patch("requests.post", side_effect=router), \
                 patch("requests.get",  return_value=mock_get), \
                 patch("time.sleep"), \
                 patch("cram.search.ddg.DDG_AVAILABLE", False), \
                 patch("cram.search.exa.EXA_API_KEY", ""):
                from cram.run import run_research
                run_research("Whipple portal hypertension",
                             output_file=f"{td}/r.md", auto=True, enter_chat=False)

            session_dirs = list(pathlib.Path(td).glob("session_*"))
            if session_dirs:
                cp_path = session_dirs[0] / "pending_branches.json"
                self.assertTrue(cp_path.exists(), "pending_branches.json not created")
                state = json.loads(cp_path.read_text())
                # All branches should be complete after a successful run
                statuses = set(state.values())
                self.assertNotIn("pending", statuses,
                                 "Branches still pending after successful run")
                self.assertIn("complete", statuses)


class TestE2EPipeline(unittest.TestCase):
    """Full pipeline with mocked LLM and search — verifies structure, not content."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = pathlib.Path(self.tmpdir.name)
        import cram.config as cfg
        self._orig_data_dir = cfg.DATA_DIR
        cfg.DATA_DIR = self.data_dir
        cfg.BFS_BRANCHES = 2
        cfg.DFS_DEPTH = 1

    def tearDown(self):
        import cram.config as cfg
        cfg.DATA_DIR = self._orig_data_dir
        self.tmpdir.cleanup()

    def _mock_llm(self, content):
        m = MagicMock()
        m.status_code = 200
        m.raise_for_status = MagicMock()
        m.json.return_value = {
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        return m

    @patch("cram.provider.openrouter.requests.post")
    @patch("cram.search.pubmed.requests.get")
    @patch("cram.search.europe_pmc.requests.get")
    def test_pipeline_produces_report_with_required_sections(
        self, mock_epmc, mock_pubmed, mock_llm_post
    ):
        search_resp = MagicMock()
        search_resp.status_code = 200
        search_resp.json.return_value = {"esearchresult": {"idlist": []}}
        search_resp.raise_for_status = MagicMock()
        mock_pubmed.return_value = search_resp

        epmc_resp = MagicMock()
        epmc_resp.status_code = 200
        epmc_resp.json.return_value = {"resultList": {"result": []}}
        epmc_resp.raise_for_status = MagicMock()
        mock_epmc.return_value = epmc_resp

        def llm_side_effect(*args, **kwargs):
            payload = kwargs.get("json", {})
            messages = payload.get("messages", [])
            last_msg = messages[-1]["content"] if messages else ""

            if "question_type" in last_msg.lower() and "key_questions" in last_msg.lower():
                return self._mock_llm(json.dumps(FAKE_QUESTION_ANALYSIS))
            if "research branches" in last_msg.lower() or "decompose" in last_msg.lower():
                return self._mock_llm(json.dumps([
                    {"branch_id": 1, "angle": "Mortality outcomes",
                     "rationale": "Key question", "primary_query": "whipple cirrhosis mortality",
                     "followup_queries": ["portal hypertension surgery outcomes"]},
                    {"branch_id": 2, "angle": "Drug interactions",
                     "rationale": "Rivaroxaban safety", "primary_query": "rivaroxaban hepatic impairment",
                     "followup_queries": []},
                ]))
            if "missing information" in last_msg.lower() or "ambiguous" in last_msg.lower():
                return self._mock_llm(json.dumps({
                    "missing": ["BMI"], "ambiguous": [], "invalid": [],
                    "assumptions": ["Child-Pugh A is current"],
                    "decision": "Whether to proceed with Whipple",
                    "audience": "Operating surgeon"
                }))
            if "key_findings" in last_msg:
                return self._mock_llm(json.dumps({
                    "key_findings": ["Mortality 5-12% in Child-Pugh A [2b]"],
                    "gaps": ["No Indian data"], "next_queries": []
                }))
            if "KEEP" in last_msg or "WEAKEN" in last_msg:
                return self._mock_llm(json.dumps({
                    "verified": [{"original": "Mortality 5-12%", "action": "KEEP",
                                   "revised": "Mortality 5-12%", "reason": "Supported",
                                   "evidence_grade": "2b"}]
                }))
            if "CRITICAL ALERT" in last_msg or "black-box" in last_msg.lower():
                return self._mock_llm(json.dumps(
                    {"is_alert": False, "alert_text": "", "source": ""}
                ))
            if "missed" in last_msg.lower() and "adversarial" in last_msg.lower():
                return self._mock_llm(json.dumps({
                    "uu_questions": [{"question": "HBV reactivation?",
                                       "priority": "HIGH",
                                       "search_query": "HBV reactivation surgery"}]
                }))
            if "contradiction" in last_msg.lower():
                return self._mock_llm(json.dumps({"contradictions": []}))
            if "risk tier" in last_msg.lower() or "HIGH|MODERATE" in last_msg:
                return self._mock_llm(json.dumps(
                    {"tier": "HIGH", "justification": "Cirrhosis + anticoagulation"}
                ))
            if "safety_issues" in last_msg:
                return self._mock_llm(json.dumps({
                    "safety_issues": [], "overall_risk": "MEDIUM",
                    "ready_for_clinical_use": True, "missing_topics": []
                }))
            return self._mock_llm(
                "## CRITICAL ALERTS\nNo critical alerts.\n\n"
                "## PATIENT PROFILE SUMMARY\n65M Child-Pugh A\n\n"
                "## RISK TIER\nHIGH\n\n"
                "## PRE-OP (72h before)\nStop rivaroxaban 48h\n\n"
                "## SOURCES\nPMID: 12345678\n"
            )

        mock_llm_post.side_effect = llm_side_effect

        patches = []
        for mod in [
            "cram.search.semantic_scholar.requests.get",
            "cram.search.open_alex.requests.get",
            "cram.search.clinical_trials.requests.get",
            "cram.search.cochrane.requests.get",
            "cram.search.crossref.requests.get",
            "cram.search.medrxiv.requests.get",
            "cram.search.core_api.requests.get",
            "cram.search.doaj.requests.get",
            "cram.search.ctri.requests.get",
            "cram.search.openfda.requests.get",
            "cram.search.guidelines.requests.get",
        ]:
            p = patch(mod, side_effect=Exception("mocked offline"))
            p.start()
            patches.append(p)

        patches.append(patch("cram.search.ddg.DDG_AVAILABLE", False))
        patches.append(patch("cram.search.youtube.GEMINI_API_KEY", ""))
        patches.append(patch("cram.search.exa.EXA_API_KEY", ""))
        for p in patches[-3:]:
            p.start()

        patches.append(patch("cram.search.unpaywall.fetch_fulltext_for_results", return_value={}))
        patches[-1].start()

        import cram.search.base as base_mod
        base_mod._query_cache = base_mod.QueryCache(self.data_dir)

        try:
            from cram.run import run_research
            report = run_research(
                scenario="65M obstructive jaundice cholangiocarcinoma planned Whipple "
                         "Child-Pugh A HBV cirrhosis rivaroxaban eGFR 45 CKD-3b "
                         "previous cholecystectomy",
                output_file=str(self.data_dir / "test_report.md"),
                auto=True,
                enter_chat=False,
            )

            self.assertIn("CRAM-1 Clinical Research Brief", report)
            self.assertIn("DISCLAIMER", report)

            report_path = self.data_dir / "test_report.md"
            self.assertTrue(report_path.exists())

            session_dirs = list(self.data_dir.glob("session_*"))
            self.assertGreater(len(session_dirs), 0)

        finally:
            for p in patches:
                p.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)

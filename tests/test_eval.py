"""tests/test_eval.py — offline tests for the eval harness (no network / no LLM)."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("OPENROUTER_API_KEY", "test-key-not-real")


class TestQueryGeneration(unittest.TestCase):
    def test_queries_from_title_splits_on_for(self):
        from cram.eval.cochrane_recall import queries_from_title
        qs = queries_from_title(
            "Galactomannan detection for invasive aspergillosis in immunocompromised patients")
        # full title kept
        self.assertTrue(any("Galactomannan detection for invasive" in q for q in qs))
        # intervention isolated
        self.assertIn("Galactomannan detection", qs)
        # no duplicates
        self.assertEqual(len(qs), len(set(q.lower() for q in qs)))

    def test_queries_from_title_no_for(self):
        from cram.eval.cochrane_recall import queries_from_title
        qs = queries_from_title("Rapid diagnostic assays")
        self.assertEqual(qs, ["Rapid diagnostic assays"])


class TestRecallMath(unittest.TestCase):
    def test_micro_and_macro_recall(self):
        import cram.eval.cochrane_recall as cr
        reviews = [
            {"review_id": "R1", "title": "t1", "included_pmids": ["1", "2", "3", "4"]},
            {"review_id": "R2", "title": "t2", "included_pmids": ["10", "20"]},
        ]
        # R1: retrieve 2/4 ; R2: retrieve 2/2
        fake = {"t1": {"1", "2", "99"}, "t2": {"10", "20"}}
        with patch.object(cr, "_retrieved_pmids_search_only",
                          side_effect=lambda title, mr: fake[title]):
            s = cr.evaluate(reviews, full=False, max_results=10)
        # micro = (2+2)/(4+2) = 4/6
        self.assertAlmostEqual(s["micro_recall"], round(4/6, 4))
        # macro = (0.5 + 1.0)/2 = 0.75
        self.assertAlmostEqual(s["macro_recall"], 0.75)
        self.assertEqual(s["total_found"], 4)
        self.assertEqual(s["per_review"][0]["n_found"], 2)


class TestQrelsParsing(unittest.TestCase):
    def test_parse_qrels_included_only_rel1(self):
        from cram.eval.build_dataset import _parse_qrels
        text = "CD1 0 111 1\nCD1 0 222 0\nCD1 0 333 1\nCD2 0 444 1\n"
        q = _parse_qrels(text)
        self.assertEqual(sorted(q["CD1"]["included"]), ["111", "333"])
        self.assertEqual(len(q["CD1"]["screened"]), 3)
        self.assertEqual(q["CD2"]["included"], ["444"])

    def test_parse_title_query(self):
        from cram.eval.build_dataset import _parse_title_query
        topic = "Topic: CD1\n\nTitle: My review title\n\nQuery:\nterm1\nterm2\n"
        title, query = _parse_title_query(topic)
        self.assertEqual(title, "My review title")
        self.assertIn("term1", query)


class TestPlantedErrorsHarness(unittest.TestCase):
    def test_catch_and_false_discard_rates(self):
        import cram.eval.planted_errors as pe
        fixtures = [{
            "id": "fx", "snippets": "snip",
            "true": ["true-A", "true-B"],
            "planted": ["fake-A", "fake-B", "fake-C"],
        }]
        # verifier "catches" a claim if it drops it (returns []).
        # Simulate: drops all planted (good) + wrongly drops one true (false discard).
        def fake_kept(finding, snippets):
            if finding.startswith("fake"):
                return False          # correctly removed
            if finding == "true-B":
                return False          # wrongly removed
            return True
        with patch.object(pe, "_kept", side_effect=fake_kept):
            s = pe.evaluate(fixtures)
        self.assertEqual(s["catch_rate"], 1.0)           # 3/3 planted caught
        self.assertEqual(s["false_discard_rate"], 0.5)   # 1/2 true dropped


if __name__ == "__main__":
    unittest.main(verbosity=2)

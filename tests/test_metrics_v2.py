import unittest
from src.common import ROOT
from src.evaluation.reproducibility import read_csv
from src.evaluation.metrics_v2 import evaluate_row, summarize, extract_entities


class MetricsV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gold = {r["id"]: r for r in read_csv(ROOT/"data/benchmark/benchmark_300.csv")}
        cls.answers = {r["question_id"]: r["answer"] for r in
                       read_csv(ROOT/"results/final_evaluation/adaptive_hybrid_graphrag_results.csv")}

    def score(self, qid, answer, **extra):
        return evaluate_row(dict(self.gold[qid], answer=answer, system="adaptive_hybrid_graphrag", **extra))

    def test_ten_files(self):
        r = self.score("dependency_analysis-040", self.answers["dependency_analysis-040"])
        self.assertEqual((r["strict_accuracy"], r["fact_recall"], r["entity_f1"]), (1, 1, 1))

    def test_prose_titles(self):
        r = self.score("issue_pr_analysis-004", self.answers["issue_pr_analysis-004"])
        self.assertEqual((r["strict_accuracy"], r["entity_f1"]), (1, 1))

    def test_number_is_not_title(self):
        self.assertEqual(self.score("issue_pr_analysis-028", "2157")["strict_accuracy"], 0)

    def test_bare_issue_number(self):
        self.assertEqual(self.score("issue_pr_analysis-030", "475")["strict_accuracy"], 1)
        self.assertEqual(self.score("issue_pr_analysis-030", "Insufficient repository evidence.")["strict_accuracy"], 0)

    def test_extra_file(self):
        r = self.score("dependency_analysis-040", self.answers["dependency_analysis-040"]+"\nsrc/wrong.py")
        self.assertEqual(r["strict_accuracy"], 0)
        self.assertEqual(r["entity_recall"], 1)
        self.assertLess(r["entity_precision"], 1)

    def test_right_file_wrong_commit(self):
        r = self.score("dependency_analysis-002", self.answers["dependency_analysis-002"]+" from commit deadbee12345678")
        self.assertEqual(r["strict_accuracy"], 0)
        self.assertTrue(r["contradictions"])

    def test_prefixed_path_not_containment(self):
        r = self.score("dependency_analysis-002", "wrong/"+self.answers["dependency_analysis-002"])
        self.assertEqual(r["strict_accuracy"], 0)

    def test_extra_issue_number(self):
        self.assertEqual(self.score("issue_pr_analysis-030", "475 and 476")["strict_accuracy"], 0)

    def test_negated_correct_file(self):
        self.assertEqual(self.score("dependency_analysis-002", "not "+self.answers["dependency_analysis-002"])["strict_accuracy"], 0)

    def test_failed_abstention(self):
        r = self.score("issue_pr_analysis-030", "Insufficient repository evidence.", retrieval_error="Timeout")
        self.assertTrue(r["is_error"])
        self.assertFalse(r["abstained"])

    def test_missing_gold_is_not_incorrect_gold(self):
        r = evaluate_row(dict(question_id="Q001", answer="something", category="Structure"))
        self.assertIsNone(r["strict_accuracy"])
        self.assertTrue(r["missing_gold"])

    def test_no_retrieval_na(self):
        r = evaluate_row(dict(self.gold["dependency_analysis-002"], answer="Insufficient repository evidence.", system="plain_llm"))
        self.assertIsNone(r["evidence_recall_at_k"])

    def test_errors_in_denominator(self):
        ok = self.score("issue_pr_analysis-030", "475")
        error = self.score("issue_pr_analysis-030", "", error="Timeout")
        summary = summarize([ok, error])[0]
        self.assertEqual(summary["strict_accuracy"], .5)
        self.assertEqual(summary["accuracy_non_error"], 1)
        self.assertEqual(summary["n_errors"], 1)

    def test_unanswerable(self):
        r = evaluate_row(dict(answer="Not found.", answerable="false", system="plain_llm"))
        self.assertEqual(r["correct_abstention"], 1)
        r = evaluate_row(dict(answer="src/fabricated.py", answerable="false", system="plain_llm"))
        self.assertEqual(r["fabrication"], 1)

    def test_dictionary_keys_are_not_symbols(self):
        _, _, predicted = extract_entities("{'name': 'Foo', 'state': 'open'}", {"answer_type": "quoted_symbol"}, ["Foo"])
        self.assertNotIn("name", predicted)
        self.assertNotIn("state", predicted)

    def test_malformed_gold_raises(self):
        with self.assertRaises(ValueError):
            evaluate_row(dict(expected_entities='[invalid', answer="x"))

    def test_uncheckable_fact_flag(self):
        r = evaluate_row(dict(expected_entities='["src/a.py"]', required_facts='["a vague fact"]', answer="src/a.py", answer_type="file_path"))
        self.assertEqual(r["unchecked_fact_count"], 1)
        self.assertIsNone(r["fact_recall"])


if __name__ == "__main__":
    unittest.main()

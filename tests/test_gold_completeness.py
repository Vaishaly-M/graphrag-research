import unittest
from src.evaluation.metrics_v2 import gold_completeness, evaluate_row


class CompletenessTests(unittest.TestCase):
    def test_query_limit_is_not_proof_of_complete_gold(self):
        row=dict(cypher="MATCH (n) RETURN n.path LIMIT 1", reference_provenance="neo4j_cypher_ground_truth",expected_entities=["src/a.py"])
        self.assertIsNone(gold_completeness(row)[0])
        row["cypher"]="MATCH (n) RETURN n.path LIMIT 20"
        self.assertTrue(gold_completeness(row)[0])

    def test_unknown_provenance(self):
        self.assertIsNone(gold_completeness(dict(expected_entities=["src/a.py"]))[0])

    def test_dual_accuracy_without_changing_gold(self):
        row=dict(expected_entities=["src/a.py"],answer_type="file_list",answer="src/a.py\nsrc/b.py")
        score=evaluate_row(row)
        self.assertEqual(score["strict_accuracy"],0)
        self.assertEqual(score["recall_accuracy"],1)
        self.assertEqual(row["expected_entities"],["src/a.py"])


if __name__ == "__main__":
    unittest.main()

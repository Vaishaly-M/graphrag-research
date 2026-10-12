import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
from scripts.derive_oracle_routes import derive, checkpoint, active_records, quota_stop
from scripts.audit_phase1b import overlaps
from src.common import ROOT
from src.llm import GeminiClient
from src.evaluation.telemetry import Measurement, measured


def record(route, correct=1, strict=1, error=False, latency=1):
    return dict(question_id="q", route=route, category="structure", source_repo="repo",
                recall_accuracy=correct, strict_accuracy=strict, is_error=error, latency_s=latency,
                latency_eligible=not error, answer_status="error" if error else "answered", attempt_number=1)


class Phase1BTests(unittest.TestCase):
    def test_provider_quota_is_logged_without_sensitive_message(self):
        def request(**kwargs):
            raise RuntimeError("429 quota exhausted secret-provider-payload")
        client = GeminiClient.__new__(GeminiClient)
        client.model, client.cache_enabled, client.cache_namespace = "fake", False, "test"
        client.cache_dir, client.interval, client._last_call = ROOT / "results/v2/tests", 0, {}
        client._key_cycle = iter(["fake"])
        client._clients = {"fake":SimpleNamespace(models=SimpleNamespace(generate_content=request))}
        base = ROOT / "results/v2/tests"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as directory:
            m = Measurement(event_path=Path(directory)/"events.jsonl")
            with measured(m), patch("src.llm.config_get", return_value=1), self.assertRaises(RuntimeError):
                client.generate("question")
            self.assertTrue(m.events[0]["quota_exhausted"])
            self.assertNotIn("secret-provider-payload", (Path(directory)/"events.jsonl").read_text())

    def test_cost_order_independent_of_cache_and_latency(self):
        rows = [record("graph", latency=100), record("vector", latency=.1), record("hybrid")]
        rows[0]["latency_eligible"] = False
        self.assertEqual(derive(rows)[0]["oracle_route"], "graph")
        rows[0]["recall_accuracy"] = 0
        self.assertEqual(derive(rows)[0]["oracle_route"], "vector")

    def test_errors_incorrect_and_best_metrics_independent(self):
        rows = [record("graph", strict=0), record("vector", error=True), record("hybrid")]
        result = derive(rows)[0]
        self.assertEqual(result["oracle_route"], "graph")
        self.assertEqual(result["oracle_best_strict_accuracy"], 1)
        for row in rows:
            row["is_error"] = True
        result = derive(rows)[0]
        self.assertTrue(result["no_route_correct"])
        self.assertEqual(result["oracle_best_accuracy"], 0)
        self.assertIsNone(result["oracle_route"])

    def test_partial_checkpoint_and_quota_replacement(self):
        base = ROOT / "results/v2/tests"
        base.mkdir(parents=True, exist_ok=True)
        history = [record("graph"), record("vector", correct=0, strict=0, error=True)]
        history[-1]["retry_events"] = [dict(quota_exhausted=True)]
        self.assertTrue(quota_stop(history[-1]))
        with tempfile.TemporaryDirectory(dir=base) as directory:
            oracle, progress = checkpoint(Path(directory), history, 1, "QUOTA_STOP")
            self.assertEqual(oracle, [])
            self.assertEqual(progress["active_errors"], 1)
            history += [record("vector"), record("hybrid")]
            oracle, progress = checkpoint(Path(directory), history, 1, "COMPLETE_DIAGNOSTIC")
            self.assertEqual(len(active_records(history)), 3)
            self.assertEqual(progress["attempts"], 4)
            self.assertEqual(progress["active_errors"], 0)
            self.assertEqual(len(oracle), 1)

    def test_shared_entity_not_whole_answer_set(self):
        a = dict(question_id="a", question="First question", source_repo="r", params='{"developer":"email:a@b.com"}')
        b = dict(question_id="b", question="Different question", source_repo="r", params='{"developer":"email:a@b.com"}')
        self.assertEqual(overlaps([a], [b])[0]["check"], "primary_entity")
        b["source_repo"] = "different"
        # Phase 1C: developer identity is global even when repository scopes differ.
        self.assertEqual(overlaps([a], [b])[0]["check"], "primary_entity")


if __name__ == "__main__":
    unittest.main()

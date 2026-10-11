import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from src.common import ROOT
from src.llm import GeminiClient, EmptyModelResponse
from src.systems.base import BaseSystem
from src.evaluation.telemetry import Measurement, measured
from src.evaluation.harness_v2 import measure_answer


class FakeSystem(BaseSystem):
    name = "fake"
    def __init__(self):
        self.fail = True
    def answer(self, question):
        if self.fail:
            raise TimeoutError("test")
        return {"answer": "475"}


class HarnessTests(unittest.TestCase):
    def test_resume_preserves_failures_and_warmup(self):
        base = ROOT / "results/v2/tests"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as directory:
            directory = Path(directory)
            benchmark = directory/"questions.csv"
            benchmark.write_text('question_id,question,expected_entities,answer_type\nq,Which issue?,475,issue_number\n')
            system = FakeSystem()
            with self.assertRaises(RuntimeError):
                system.run(benchmark, directory/"run", repeats=2, discard_first_run=True)
            system.fail = False
            system.run(benchmark, directory/"run", repeats=2, discard_first_run=True)
            rows = [json.loads(line) for line in (directory/"run/fake_results.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows), 4)
            self.assertEqual(sum(r["superseded"] for r in rows), 2)
            self.assertEqual([r["attempt_number"] for r in rows], [1, 1, 2, 2])
            self.assertEqual(sum(r["warmup"] for r in rows), 2)
            system.run(benchmark, directory/"run", repeats=2, discard_first_run=True)
            self.assertEqual(len((directory/"run/fake_results.jsonl").read_text().splitlines()), 4)

    def client(self, response):
        client = GeminiClient.__new__(GeminiClient)
        client.model = "fake"
        client.cache_enabled = False
        client.cache_namespace = "fake"
        client.cache_dir = Path("unused")
        client.interval = 0
        client._last_call = {}
        client._key_cycle = iter(["fake"])
        client._clients = {"fake": SimpleNamespace(models=SimpleNamespace(generate_content=response))}
        return client

    def test_empty_model_response_raises(self):
        client = self.client(lambda **kwargs: SimpleNamespace(text="  "))
        with tempfile.TemporaryDirectory() as directory:
            m = Measurement(event_path=Path(directory)/"events.jsonl")
            with measured(m), self.assertRaises(EmptyModelResponse):
                client.generate("test")
            self.assertEqual(m.n_attempts, 1)
            self.assertEqual(m.events[0]["status"], "error")

    def test_swallowed_llm_error_not_abstention(self):
        client = self.client(lambda **kwargs: SimpleNamespace(text=""))
        class Swallow(BaseSystem):
            name = "swallow"
            def answer(self, question):
                try:
                    client.generate("x")
                except EmptyModelResponse:
                    pass
                return {"answer": "Insufficient repository evidence."}
        with tempfile.TemporaryDirectory() as directory:
            result, _ = measure_answer(Swallow(), "q", "x", event_path=Path(directory)/"events.jsonl")
        self.assertEqual(result["answer_status"], "error")
        self.assertEqual(result["answer"], "")

    def test_cache_key_includes_params(self):
        client = self.client(lambda **kwargs: None)
        self.assertNotEqual(client._cache_path("x", 0, 100), client._cache_path("x", 1, 100))
        self.assertNotEqual(client._cache_path("x", 0, 100), client._cache_path("y", 0, 100))

    def test_six_attempts_and_separate_backoff_accounting(self):
        clock = [100.0]
        def request(**kwargs):
            clock[0] += 2.0
            raise TimeoutError("timeout; retry-after: 3s")
        def sleep(seconds):
            clock[0] += seconds
        fake_time = SimpleNamespace(perf_counter=lambda: clock[0], monotonic=lambda: clock[0], sleep=sleep)
        client = self.client(request)
        client.interval = 6
        client._last_call = {"fake": 100.0}
        with tempfile.TemporaryDirectory() as directory:
            m = Measurement(event_path=Path(directory)/"events.jsonl")
            with measured(m), patch("src.llm.time", fake_time), patch("src.llm.random.random", return_value=0), self.assertRaises(TimeoutError):
                client.generate("test")
        self.assertEqual(m.n_attempts, 6)
        self.assertEqual(m.llm_time_s, 12)
        self.assertEqual(m.pacing_sleep_s, 6)
        self.assertEqual(m.backoff_sleep_s, 34)  # max(1,3)+max(2,3)+4+8+16
        self.assertEqual(len(m.events), 6)
        self.assertEqual(m.events[0]["retry_after_s"], 3)

    def test_retried_success_remains_latency_eligible(self):
        m = Measurement()
        m.events = [{"status": "error"}, {"status": "ok"}]
        m.llm_time_s, m.backoff_sleep_s, m.n_attempts = 4, 2, 2
        timing = m.timing(6)
        self.assertTrue(timing["latency_eligible"])
        self.assertEqual(timing["latency_s"], 4)

    def test_cached_response_makes_no_request(self):
        client = self.client(lambda **kwargs: self.fail("cache hit made an API request"))
        with tempfile.TemporaryDirectory() as directory:
            client.cache_dir = Path(directory)
            client.cache_enabled = True
            path = client._cache_path("test", .2, 1024)
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"answer": "cached answer"}))
            m = Measurement(event_path=Path(directory)/"events.jsonl")
            with measured(m):
                self.assertEqual(client.generate("test"), "cached answer")
            self.assertEqual(m.n_attempts, 0)
            self.assertEqual(m.n_cache_hits, 1)
            self.assertFalse(m.timing(.1)["latency_eligible"])

    def test_explicit_system_error_is_preserved(self):
        class Reported(BaseSystem):
            name = "reported"
            def answer(self, question):
                return dict(answer="Insufficient repository evidence.", error="failed")
        result, _ = measure_answer(Reported(), "q", "x")
        self.assertEqual(result["answer_status"], "error")
        self.assertEqual(result["error_type"], "SystemReportedError")

    def test_missing_id_fails_loudly(self):
        with self.assertRaises(ValueError):
            BaseSystem._validate_benchmark_rows([{"question": "q"}], Path("test.csv"))

    def test_swallowed_graph_failure(self):
        class Graph:
            def query(self, *args, **kwargs):
                raise TimeoutError("test")
        class Swallow(BaseSystem):
            name = "swallow"
            graph = Graph()
            def answer(self, question):
                try:
                    self.graph.query("MATCH")
                except TimeoutError:
                    pass
                return {"answer": "Insufficient repository evidence."}
        result, _ = measure_answer(Swallow(), "q", "x")
        self.assertEqual(result["answer_status"], "error")
        self.assertIn("TimeoutError", result["retrieval_error"])


if __name__ == "__main__":
    unittest.main()

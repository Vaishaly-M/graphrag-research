"""Approximately 60 physical requests, with cache and stage/attempt records."""
import argparse
import importlib
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import ROOT
from src.llm import GeminiClient
from src.systems.base import BaseSystem
from src.systems.prompts import ANSWER_TEMPERATURE, ANSWER_MAX_OUTPUT_TOKENS
from src.evaluation.harness_v2 import measure_answer
from src.evaluation.reproducibility import read_csv, write_csv, snapshot, save_snapshot, source_hashes


class Probe(BaseSystem):
    def __init__(self, system, way, index, qid):
        self.system = system
        self.llm = system.llm
        self.name = system.name
        self.way = way
        self.index = index
        self.qid = qid

    def answer(self, question):
        if self.way == "trivial_llm":
            return {"answer": self.llm.generate(f"Reply only OK. Probe {self.name} {self.qid}.",
                    temperature=ANSWER_TEMPERATURE, max_output_tokens=ANSWER_MAX_OUTPUT_TOKENS)}
        if self.way == "retrieval_only":
            from src.systems.retrieval_core import repo_from_question
            evidence = self.system.vector_store.search(question, k=10, repository=repo_from_question(question))
            return dict(answer="retrieval completed", retrieval_count=len(evidence))
        return self.system.answer(question)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", default="data/benchmark/splits/hidden_test_questions.csv")
    parser.add_argument("--systems", nargs="+", default=["plain_llm", "vector_rag"], choices=["plain_llm", "vector_rag"])
    parser.add_argument("--output", default="results/v2/latency_probe.csv")
    parser.add_argument("--ways", nargs="+", choices=["trivial_llm", "retrieval_only", "full_system"])
    parser.add_argument("--max-requests", type=int, default=60, choices=range(1, 62),
                        help="Persistent attempt cap; one extra attempt may finish a retried probe")
    args = parser.parse_args()
    path = ROOT / args.output
    if not path.resolve().is_relative_to((ROOT / "results/v2").resolve()):
        parser.error("output must be under results/v2")
    if (ROOT / "results/v2/vector_index/manifest.json").exists():
        os.environ.setdefault("VECTOR_INDEX_DIR", str(ROOT / "results/v2/vector_index"))
    benchmark = ROOT / args.benchmark
    questions = read_csv(benchmark)[:10]
    output = read_csv(path) if path.exists() else []
    done = {(r["system"], r["question_id"], r["way"]) for r in output if r.get("answer_status") != "error"}
    # Count all past actual attempts, including failed ones, on restart.
    GeminiClient.request_budget = args.max_requests
    GeminiClient.budget_file = path.parent / "latency_probe" / "request_budget.json"
    reserved = json.loads(GeminiClient.budget_file.read_text()).get("requests_reserved", 0) if GeminiClient.budget_file.exists() else 0
    GeminiClient.requests_used = max(reserved, sum(int(r["n_attempts"]) for r in output))
    for system_name in args.systems:
        directory = path.parent / "latency_probe" / system_name / ("invocation_" + str(len(output)))
        save_snapshot(directory, snapshot(benchmark, system_name, questions=10,
            ways=args.ways or ["trivial_llm", "retrieval_only", "full_system"],
            physical_request_budget=args.max_requests, source_hashes=source_hashes()))
        try:
            system = importlib.import_module("src.systems." + system_name).System()
            system.llm.cache_dir = path.parent / "latency_probe" / "response_cache"
            system.llm.cache_namespace = system_name
        except Exception as exc:
            # Setup failure is explicit, not a fabricated model measurement.
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "setup_error.json").write_text(json.dumps(dict(error_type=type(exc).__name__)), encoding="utf-8")
            raise
        ways = ["trivial_llm", "full_system"] if system_name == "plain_llm" else ["trivial_llm", "retrieval_only", "full_system"]
        if args.ways:
            ways = [way for way in ways if way in args.ways]
        for i, row in enumerate(questions):
            qid = row.get("question_id") or row["id"]
            for way in ways:
                if (system_name, qid, way) in done:
                    continue
                probe = Probe(system, way, i, qid)
                result, measurement = measure_answer(probe, qid, row["question"])
                for old in output:
                    if (old["system"], old["question_id"], old["way"]) == (system_name, qid, way):
                        old["superseded"] = True
                record = dict(system=system_name, question_id=qid, way=way, superseded=False, **result)
                record["attempt_events"] = measurement.events
                record["six_attempts_used"] = any(e.get("attempt") == 6 for e in measurement.events)
                output.append(record)
                write_csv(path, output)
                print(f"{system_name} {qid} {way}: {result['answer_status']} wall={result['total_wall_s']:.2f}s attempts={result['n_attempts']}", flush=True)
    if any(r.get("answer_status") == "error" and str(r.get("superseded")).lower() != "true" for r in output):
        raise SystemExit("Probe contains execution errors; see the CSV and attempt events")


if __name__ == "__main__":
    main()

"""Measure all forced routes on router-tuning and derive an empirical oracle."""
import argparse
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import ROOT, append_jsonl, read_jsonl
from src.evaluation.reproducibility import read_csv, write_csv, sha256, snapshot, save_snapshot, source_hashes
from src.evaluation.harness_v2 import measure_answer
from src.evaluation.metrics_v2 import evaluate_row
from src.systems.router_v2 import Decision, ROUTES


def clean_timing(row):
    """Oracle cost selection excludes cache hits, errors and retried calls."""
    return bool(row.get("latency_eligible")) and not row.get("is_error") and not any(
        event.get("status") == "error" for event in row.get("retry_events", []))


def derive(rows):
    groups = {}
    for row in rows:
        key = row["question_id"]
        route = row["route"]
        if route in groups.setdefault(key, {}):
            raise ValueError("Duplicate forced-route outcome")
        groups[key][route] = row
    output = []
    for qid, routes in groups.items():
        if set(routes) != set(ROUTES):
            raise ValueError("Oracle requires all three routes for every question")
        correct = [r for r in routes.values() if r["recall_accuracy"] == 1 and not r["is_error"]]
        clean = [r for r in correct if clean_timing(r)]
        if correct and len(clean) != len(correct):
            raise ValueError("A correct route lacks clean timing; cannot identify the cheapest route")
        best = min(clean, key=lambda r:(float(r["latency_s"]), ROUTES.index(r["route"]))) if clean else None
        output.append(dict(question_id=qid, oracle_route=best["route"] if best else None,
            oracle_best_accuracy=max(r["recall_accuracy"] or 0 for r in routes.values()),
            oracle_best_strict_accuracy=max(r["strict_accuracy"] or 0 for r in routes.values()),
            cheapest_correct_latency_s=best["latency_s"] if best else None))
    return output


class ForcedRouter:
    def __init__(self, route):
        self.route = route
    def classify(self, question):
        return Decision(self.route, self.route, 1., {r:float(r==self.route) for r in ROUTES}, {}, [], "forced_oracle", 0.)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", default="route_outcomes")
    parser.add_argument("--derive-only", action="store_true")
    args = parser.parse_args()
    if Path(args.run_name).name != args.run_name:
        parser.error("run-name must be a single name")
    benchmark = ROOT/"data/benchmark/splits_v2/router-tuning.csv"
    manifest = json.loads((benchmark.parent/"manifest.json").read_text())
    if sha256(benchmark) != manifest["splits"]["router-tuning"]["sha256"]:
        raise RuntimeError("Tuning split hash mismatch")
    output = ROOT/"results/v2/phase2"/args.run_name
    path = output/"outcomes.jsonl"
    records = read_jsonl(path)
    if not args.derive_only:
        index = ROOT/"results/v2/vector_index"
        index_manifest = json.loads((index/"manifest.json").read_text())
        if index_manifest.get("diagnostic_only"):
            raise RuntimeError("Diagnostic index forbidden")
        os.environ["VECTOR_INDEX_DIR"] = str(index)
        save_snapshot(output, snapshot(benchmark, "forced_route_oracle", source_hashes=source_hashes(), safety_fallback=False,
            retrieval_warmup="Load index, embed generic warm-up text and issue RETURN 1 before timing"))
        from src.systems.adaptive_hybrid_graphrag_v2 import System
        system = System(router=ForcedRouter("graph"), enable_safety_fallback=False)
        system.vector_store.load()
        system.vector_store.model.encode(["retrieval warm-up"], normalize_embeddings=True)
        system.graph.query("RETURN 1 AS ready")
        system.llm.cache_dir = output/"response_cache"
        done = {(r["question_id"],r["route"]) for r in records}
        try:
            for row in read_csv(benchmark):
                qid = row["question_id"]
                for route in ROUTES:
                    if (qid,route) in done:
                        continue
                    system.router = ForcedRouter(route)
                    system.llm.cache_namespace = route
                    result, measurement = measure_answer(system, qid, row["question"])
                    metrics = evaluate_row(dict(row, **result), system.name)
                    record = dict(row)
                    record.update(result)
                    record.update(metrics)
                    record.update(route=route, retry_events=measurement.events)
                    records.append(record)
                    append_jsonl(path, record)
                    write_csv(output/"outcomes.csv", records)
                    print(qid, route, record["answer_status"], record["recall_accuracy"], flush=True)
        finally:
            system.graph.close()
    oracle = derive(records)
    if len(oracle) != manifest["splits"]["router-tuning"]["count"]:
        raise RuntimeError("Incomplete oracle outcomes; refusing to publish labels")
    write_csv(output/"oracle_routes.csv", oracle)


if __name__ == "__main__":
    main()

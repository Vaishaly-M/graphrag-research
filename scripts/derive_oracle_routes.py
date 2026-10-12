"""Phase 1C: checkpoint both forced-route modes on the final router-tuning split only."""
import argparse
import json
import os
import sys
import shutil
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import ROOT, append_jsonl, read_jsonl
from src.evaluation.reproducibility import read_csv, write_csv, sha256, snapshot, save_snapshot, source_hashes
from src.evaluation.harness_v2 import measure_answer
from src.evaluation.metrics_v2 import evaluate_row
from src.systems.router_v2 import Decision, ROUTES


def clean_timing(row):
    return bool(row.get("latency_eligible")) and not row.get("is_error") and not any(
        e.get("status") == "error" for e in row.get("retry_events", []))


def derive(rows):
    """Use the predeclared ordinal cost graph < vector < hybrid, never wall time."""
    groups = {}
    for row in rows:
        routes = groups.setdefault(row["question_id"], {})
        if row["route"] in routes:
            raise ValueError("Duplicate forced-route outcome")
        routes[row["route"]] = row
    output = []
    for qid, routes in groups.items():
        if set(routes) != set(ROUTES):
            raise ValueError("Oracle requires all three routes for every question")
        correct = [r for r in ROUTES if routes[r]["recall_accuracy"] == 1 and not routes[r]["is_error"]]
        best = correct[0] if correct else None
        result = dict(question_id=qid, category=routes["graph"].get("category"),
                      source_repo=routes["graph"].get("source_repo"), oracle_route=best,
                      oracle_best_accuracy=max(0 if r["is_error"] else (r["recall_accuracy"] or 0) for r in routes.values()),
                      oracle_best_strict_accuracy=max((0 if r["is_error"] else r["strict_accuracy"] for r in routes.values()
                                                     if r["strict_accuracy"] is not None), default=None),
                      no_route_correct=not correct, cheapest_correct_latency_s=routes[best]["latency_s"] if best else None)
        for route, row in routes.items():
            for field in ("recall_accuracy", "strict_accuracy", "latency_s", "answer_status", "latency_eligible"):
                result[route + "_" + field] = row.get(field)
        output.append(result)
    return output


def active_records(history):
    """Append-only attempts; latest completed attempt per question/route is active."""
    active = {}
    for row in history:
        active[(row["question_id"], row["route"])] = row
    return list(active.values())


def quota_stop(record):
    return record.get("answer_status") == "error" and any(e.get("quota_exhausted") for e in record.get("retry_events", []))


def atomic_json(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2)+"\n", encoding="utf-8")
    # Windows readers/virus scanners can briefly deny replacement of an open file.
    # Keep the durable JSONL journal; retry only this local atomic rename, never a model call.
    for attempt in range(20):
        try:
            temp.replace(path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(.1)


def checkpoint(output, history, total, status):
    records = active_records(history)
    counts = Counter(r["question_id"] for r in records)
    complete = {q for q, n in counts.items() if n == len(ROUTES)}
    oracle = derive([r for r in records if r["question_id"] in complete])
    write_csv(output / "outcomes.csv", records)
    write_csv(output / "oracle_routes_partial.csv", oracle, fields=None if oracle else ["question_id", "oracle_route"])
    progress = dict(status=status, total_questions=total, questions_with_all_routes=len(complete),
                    questions_without_errors=sum(all(not r["is_error"] for r in records if r["question_id"] == q) for q in complete),
                    route_outcomes=len(records), attempts=len(history), active_errors=sum(r["is_error"] for r in records),
                    diagnostic_only=True, cost_order=list(ROUTES), latency_excludes="pacing and backoff",
                    resume_command="python -B scripts/derive_oracle_routes.py --run-name " + output.name +
                    (" --no-templates" if any(r.get("mode") == "no-templates" for r in records) else " --extend-phase1b"))
    atomic_json(output / "progress.json", progress)
    route_summary = []
    for category in ["ALL"] + sorted({r["category"] for r in records}):
        subset = [r for r in records if category == "ALL" or r["category"] == category]
        for route in ROUTES:
            part = [r for r in subset if r["route"] == route]
            if not part:
                continue
            times = [r["latency_s"] for r in part if clean_timing(r)]
            strict = [r["strict_accuracy"] for r in part if r["strict_accuracy"] is not None]
            route_summary.append(dict(category=category, route=route, n=len(part),
                recall_accuracy=sum(r["recall_accuracy"] or 0 for r in part)/len(part),
                strict_accuracy=sum(strict)/len(strict) if strict else None, n_gold_complete=len(strict),
                errors=sum(r["is_error"] for r in part),
                mean_clean_latency_s=sum(times)/len(times) if times else None, clean_latency_n=len(times)))
    write_csv(output / "route_summary.csv", route_summary,
              fields=None if route_summary else ["category", "route", "n"])
    distributions = []
    for category in ["ALL"] + sorted({r["category"] for r in oracle}):
        subset = [r for r in oracle if category == "ALL" or r["category"] == category]
        counts = Counter(r["oracle_route"] or "none" for r in subset)
        distributions.append(dict(category=category, n=len(subset), **{r:counts[r] for r in (*ROUTES, "none")},
                                  vector_cheapest_rate=counts["vector"]/len(subset) if subset else None))
    write_csv(output / "oracle_distribution.csv", distributions)
    return oracle, progress


class ForcedRouter:
    def __init__(self, route):
        self.route = route

    def classify(self, question):
        return Decision(self.route, self.route, 1., {r:float(r == self.route) for r in ROUTES}, {}, [], "forced_oracle", 0.)


def seed_cache(target):
    """Reuse exact content-addressed responses; never treat a cache hit as clean latency."""
    source = ROOT / "results/v2/phase1b/route_outcomes/response_cache/shared"
    (target/"shared").mkdir(parents=True, exist_ok=True)
    for path in source.glob("*.json"):
        dest = target/"shared"/path.name
        if not dest.exists():
            shutil.copyfile(path,dest)


def import_phase1b(output, history, benchmark_rows):
    """Extend retained v1 outcomes unchanged except the explicitly revised strict reporting policy."""
    source = ROOT / "results/v2/phase1b/route_outcomes"
    old_config = json.loads((source/"config_snapshot.json").read_text())
    new_config = json.loads((output/"config_snapshot.json").read_text())
    for key in ("model_name", "config", "index_file_hash", "index_manifest_hash", "temperature"):
        if old_config[key] != new_config[key]:
            raise RuntimeError("Cannot reuse Phase 1B: changed " + key)
    # Only the no-templates guard and descriptive return field changed in production inference.
    for name,digest in old_config["source_hashes"].items():
        if name.startswith("src/") and name != "src/systems/adaptive_hybrid_graphrag_v2.py" and sha256(ROOT/name) != digest:
            raise RuntimeError("Cannot reuse Phase 1B: changed production source " + name)
    v1 = {r["question_id"]:r for r in read_csv(ROOT/"data/benchmark/splits_v2/router-tuning_v1.csv")}
    current = {r["question_id"]:r for r in benchmark_rows}
    done = {(r["question_id"],r["route"]) for r in history}
    for row in active_records(read_jsonl(source/"outcomes.jsonl")):
        qid = row["question_id"]
        if qid not in current or (qid,row["route"]) in done:
            continue
        if v1[qid] != {k:current[qid][k] for k in v1[qid]}:
            raise RuntimeError("Retained v1 row changed: " + qid)
        record = dict(row, mode="with-templates", imported=True,
                      imported_from=str((source/"outcomes.jsonl").relative_to(ROOT)),
                      imported_source_sha256=sha256(source/"outcomes.jsonl"))
        record["frozen_set_strict_accuracy"] = record["strict_accuracy"]
        if record["gold_complete"] is not True:
            record["strict_accuracy"] = None
        history.append(record)
        append_jsonl(output/"outcomes.jsonl",record)
        if row["route"] == "hybrid":
            checkpoint(output,history,len(current),"IMPORTING_PHASE1B")
    return history


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", default="route_outcomes")
    parser.add_argument("--derive-only", action="store_true")
    parser.add_argument("--allow-overlap-diagnostic", action="store_true")
    parser.add_argument("--no-templates", action="store_true")
    parser.add_argument("--extend-phase1b", action="store_true")
    args = parser.parse_args()
    if Path(args.run_name).name != args.run_name or args.run_name in {".", ".."}:
        parser.error("run-name must be a single name")
    benchmark = ROOT / "data/benchmark/splits_v2/router-tuning.csv"
    manifest = json.loads((benchmark.parent / "manifest.json").read_text())
    split_hash = sha256(benchmark)
    if split_hash != manifest["splits"]["router-tuning"]["sha256"]:
        raise RuntimeError("Tuning split hash mismatch")
    if args.no_templates and args.extend_phase1b:
        parser.error("Cannot import template-enabled outcomes into no-templates mode")
    mode = "no-templates" if args.no_templates else "with-templates"
    audit_path = ROOT / "results/v2/phase1c/disjointness.json"
    audit = json.loads(audit_path.read_text())
    if audit["hashes"]["router-tuning"] != split_hash:
        raise RuntimeError("Stale split audit")
    if audit["status"] == "FAIL" and not args.allow_overlap_diagnostic:
        raise RuntimeError("Split overlap detected: diagnostic-only authorization required")
    benchmark_rows = read_csv(benchmark)
    ids = {r["question_id"] for r in benchmark_rows}
    if len(ids) != len(benchmark_rows) or len(ids) != manifest["splits"]["router-tuning"]["count"]:
        raise RuntimeError("Duplicate IDs or split count mismatch")
    output = ROOT / "results/v2/phase1c" / args.run_name
    output.mkdir(parents=True, exist_ok=True)
    path = output / "outcomes.jsonl"
    history = read_jsonl(path)
    if any(r["question_id"] not in ids or r["route"] not in ROUTES for r in history):
        raise RuntimeError("Checkpoint contains unexpected questions/routes")
    if not args.derive_only:
        index = ROOT / "results/v2/vector_index"
        index_manifest = json.loads((index / "manifest.json").read_text())
        if index_manifest.get("diagnostic_only") or any(sha256(index / name) != index_manifest[field]
                for name, field in (("index.faiss", "index_sha256"), ("docs.json", "docs_sha256"))):
            raise RuntimeError("Diagnostic or corrupt index forbidden")
        os.environ["VECTOR_INDEX_DIR"] = str(index)
        from src.systems.prompts import ADAPTIVE_FINAL_ANSWER, ANSWER_TEMPERATURE, ANSWER_MAX_OUTPUT_TOKENS
        from src.systems.retrieval_core import MAX_FINAL_EVIDENCE
        save_snapshot(output, snapshot(benchmark, "forced_route_oracle_phase1c", source_hashes=source_hashes(),
            safety_fallback=False, template_shortcuts=not args.no_templates, mode=mode, route_cost_order=list(ROUTES),
            evidence_budget=dict(max_final_items=MAX_FINAL_EVIDENCE, context_token_cap=None,
                                 note="Identical existing fusion limit for all routes; no independent context-token cap introduced"),
            answer_prompt=ADAPTIVE_FINAL_ANSWER, answer_temperature=ANSWER_TEMPERATURE,
            answer_max_output_tokens=ANSWER_MAX_OUTPUT_TOKENS,
            strict_policy="Only gold_complete=true; N/A otherwise", imported_phase1b=args.extend_phase1b,
            diagnostic_only=True, split_audit_sha256=sha256(audit_path), overlap_authorized=args.allow_overlap_diagnostic,
            cache_key="model, generation parameters, prompt SHA-256; shared across routes",
            retrieval_warmup="Load index, embed generic warm-up text and issue RETURN 1 before timing"))
        # Existing production retrieval/answering implementation; no router training or Phase 2 commands.
        from src.systems.adaptive_hybrid_graphrag_v2 import System
        from src.systems.adaptive_hybrid_graphrag import AblationConfig
        if args.extend_phase1b:
            history = import_phase1b(output, history, benchmark_rows)
        cache = ROOT / "results/v2/phase1c/response_cache"
        seed_cache(cache)
        system = System(router=ForcedRouter("graph"), enable_safety_fallback=False,
                        ablation=AblationConfig(no_templates=args.no_templates))
        try:
            system.vector_store.load()
            system.vector_store.model.encode(["retrieval warm-up"], normalize_embeddings=True)
            system.graph.query("RETURN 1 AS ready")
            system.llm.cache_dir = cache
            system.llm.cache_namespace = "shared"
            system.llm.cache_enabled = True
            active = {(r["question_id"], r["route"]):r for r in active_records(history)}
            for row in benchmark_rows:
                qid = row["question_id"]
                for route in ROUTES:
                    prior = active.get((qid, route))
                    # Quota failures are retryable on the next invocation. Other errors remain incorrect.
                    if prior is not None and not prior.get("quota_stop"):
                        continue
                    attempt = 1 + max((r["attempt_number"] for r in history
                                       if r["question_id"] == qid and r["route"] == route), default=0)
                    append_jsonl(output / "attempts.jsonl", dict(question_id=qid, route=route,
                                 attempt_number=attempt, status="started"))
                    system.router = ForcedRouter(route)
                    result, measurement = measure_answer(system, qid, row["question"], attempt_number=attempt,
                                                          event_path=output / "llm_events.jsonl")
                    metrics = evaluate_row({**row, **result}, system.name)
                    record = {**row, **result, **metrics, "route":route, "attempt_number":attempt,
                              "retry_events":measurement.events, "mode":mode, "imported":False}
                    record["frozen_set_strict_accuracy"] = record["strict_accuracy"]
                    if record["gold_complete"] is not True:
                        record["strict_accuracy"] = None
                    record["quota_stop"] = quota_stop(record)
                    history.append(record)
                    append_jsonl(path, record)
                    append_jsonl(output / "attempts.jsonl", dict(question_id=qid, route=route,
                                 attempt_number=attempt, status=record["answer_status"]))
                    oracle, progress = checkpoint(output, history, len(ids), "QUOTA_STOP" if record["quota_stop"] else "RUNNING")
                    print(qid, route, record["answer_status"], "recall=", record["recall_accuracy"],
                          "complete=", progress["questions_with_all_routes"], flush=True)
                    if record["quota_stop"]:
                        print("Provider quota/rate limit exhausted after configured retries. Checkpoint saved; resume later.", flush=True)
                        return 2
        except BaseException:
            checkpoint(output, history, len(ids), "INTERRUPTED")
            raise
        finally:
            system.graph.close()
    oracle, progress = checkpoint(output, history, len(ids), "COMPLETE_DIAGNOSTIC")
    if len(oracle) != len(ids):
        checkpoint(output, history, len(ids), "INCOMPLETE")
        raise RuntimeError("Incomplete oracle outcomes; refusing to publish full labels")
    if any(r.get("quota_stop") for r in active_records(history)):
        checkpoint(output, history, len(ids), "QUOTA_STOP")
        return 2
    write_csv(output / "oracle_routes.csv", oracle)
    if progress["active_errors"]:
        checkpoint(output, history, len(ids), "COMPLETE_WITH_ERRORS_DIAGNOSTIC")
        print(f"FAIL: {progress['active_errors']} route errors counted as incorrect", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

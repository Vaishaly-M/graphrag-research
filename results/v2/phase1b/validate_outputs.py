"""Validate existing Phase 1B outputs; no model calls and no held-out evaluation."""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from src.evaluation.reproducibility import read_csv, sha256, source_hashes
from src.common import read_jsonl
from scripts.derive_oracle_routes import active_records, derive

OUT = ROOT / "results/v2/phase1b"
RUN = OUT / "route_outcomes"


def main():
    config = json.loads((RUN / "config_snapshot.json").read_text())
    audit = json.loads((OUT / "disjointness.json").read_text())
    progress = json.loads((RUN / "progress.json").read_text())
    rows = read_csv(ROOT / "data/benchmark/splits_v2/router-tuning.csv")
    ids = {r["question_id"] for r in rows}
    history = read_jsonl(RUN / "outcomes.jsonl")
    records = active_records(history)
    checks = {}
    checks["split_hashes_unchanged"] = all(sha256(ROOT / "data/benchmark/splits_v2" / (name+".csv")) == digest
                                          for name, digest in audit["hashes"].items())
    checks["source_hashes_match_run"] = config["source_hashes"] == source_hashes()
    checks["only_router_tuning_outcomes"] = all(r["question_id"] in ids for r in records)
    checks["no_route_escalation"] = all(r["executed_retrieval_route"] == r["route"] for r in records if not r["is_error"])
    checks["errors_incorrect"] = all(r["recall_accuracy"] == r["strict_accuracy"] == 0 for r in records if r["is_error"])
    checks["latency_excludes_waits"] = all(abs(r["latency_s"] - max(0, r["total_wall_s"]-r["sleep_wait_s"])) < 1e-7 for r in records)
    counts = Counter(r["question_id"] for r in records)
    full = [r for r in records if counts[r["question_id"]] == 3]
    oracle = {r["question_id"]:r for r in derive(full)}
    checks["oracle_dominates_both_metrics"] = all(
        oracle[r["question_id"]]["oracle_best_accuracy"] >= (r["recall_accuracy"] or 0) and
        oracle[r["question_id"]]["oracle_best_strict_accuracy"] >= (r["strict_accuracy"] or 0) for r in full)
    checks["completed_question_count_matches"] = len(oracle) == progress["questions_with_all_routes"]
    checks["run_is_complete_or_quota_stopped"] = progress["status"] in {
        "COMPLETE_DIAGNOSTIC", "COMPLETE_WITH_ERRORS_DIAGNOSTIC", "QUOTA_STOP"}
    checks["all_70_if_complete"] = len(records) == 210 if progress["status"].startswith("COMPLETE") else True
    attempts = read_jsonl(RUN / "attempts.jsonl")
    checks["attempt_starts_and_completions_logged"] = all(
        sum(e["question_id"] == r["question_id"] and e["route"] == r["route"] and
            e["attempt_number"] == r["attempt_number"] for e in attempts) == 2 for r in history)
    checks["api_attempts_logged"] = all(r["n_attempts"] == sum(e["status"] != "cache_hit" for e in r["retry_events"]) for r in history)
    checks["api_event_file_matches_records"] = len(read_jsonl(RUN / "llm_events.jsonl")) == sum(len(r["retry_events"]) for r in history)
    saved = {r["question_id"]:r for r in read_csv(RUN / ("oracle_routes.csv" if progress["status"].startswith("COMPLETE") else "oracle_routes_partial.csv"))}
    checks["saved_oracle_matches_derivation"] = set(saved) == set(oracle) and all(
        (saved[q]["oracle_route"] or None) == r["oracle_route"] and
        float(saved[q]["oracle_best_accuracy"]) == r["oracle_best_accuracy"] and
        float(saved[q]["oracle_best_strict_accuracy"]) == r["oracle_best_strict_accuracy"] for q,r in oracle.items())
    result = dict(checks=checks, all_pass=all(checks.values()), outcome_count=len(records),
                  complete_questions=len(oracle), api_attempts=sum(r["n_attempts"] for r in history),
                  cache_hits=sum(r["n_cache_hits"] for r in history),
                  scope="Integrity checks only; split disjointness remains FAIL")
    (OUT / "validation.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["all_pass"]:
        raise RuntimeError("Phase 1B output integrity failure")


if __name__ == "__main__":
    main()

"""Strict route-label diagnostics, with complete eight-system coverage checks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from scripts.prepare_routing_evaluation import ROOT, SYSTEMS, read_csv, validate_questions


def collect(results_dir, questions, repeats, require_no_errors=False):
    ids = {row["id"] for row in questions}
    expected = {(qid, repeat) for qid in ids for repeat in range(1, repeats + 1)}
    frames = {}
    for system in SYSTEMS:
        frame = pd.read_csv(results_dir / f"{system}_results.csv", dtype={"question_id": str})
        if frame.duplicated(["question_id", "run_id"]).any():
            raise ValueError(f"{system}: duplicate question/repeat keys")
        actual = set(zip(frame.question_id, frame.run_id))
        if actual != expected:
            raise ValueError(f"{system}: missing {len(expected - actual)}, extra {len(actual - expected)} question/repeat keys")
        if set(frame.system) != {system}:
            raise ValueError(f"{system}: wrong system labels")
        if require_no_errors and frame.error.fillna("").str.strip().ne("").any():
            raise ValueError(f"{system}: execution errors remain; resume before comparison")
        frames[system] = frame
    return frames


def diagnostics(frame, questions):
    routes = ["graph", "vector", "hybrid"]
    gold = {row["id"]: row["expected_retrieval_route"] for row in questions}
    frame = frame.copy()
    frame["expected_route"] = frame.question_id.map(gold)
    frame["selected_route"] = frame.selected_retrieval_route.fillna("missing").str.lower().str.strip()
    frame.loc[~frame.selected_route.isin(routes), "selected_route"] = "missing"
    confusion = pd.crosstab(frame.expected_route, frame.selected_route).reindex(
        index=routes, columns=routes + ["missing"], fill_value=0)
    metrics = []
    for route in routes:
        tp = int(confusion.loc[route, route])
        support = int(confusion.loc[route].sum())
        predicted = int(confusion[route].sum())
        precision = tp / predicted if predicted else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        metrics.append(dict(route=route, support=support, precision=precision, recall=recall, f1=f1))
    summary = {
        "rows": len(frame), "questions": frame.question_id.nunique(),
        "strict_route_label_agreement": float((frame.expected_route == frame.selected_route).mean()),
        "macro_f1": sum(row["f1"] for row in metrics) / 3,
        "interpretation": "Agreement with category-derived route proxies, not optimal-action accuracy",
    }
    return frame, confusion, pd.DataFrame(metrics), summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--require-no-errors", action="store_true")
    args = parser.parse_args()
    if args.repeats < 1:
        raise ValueError("repeats must be positive")
    questions = read_csv(ROOT / "data/benchmark/splits/hidden_test_questions.csv")
    validate_questions(questions)
    frames = collect(ROOT / args.results_dir, questions, args.repeats, args.require_no_errors)
    frame, confusion, metrics, summary = diagnostics(frames["adaptive_hybrid_graphrag"], questions)
    output = ROOT / args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    confusion.to_csv(output / "routing_confusion.csv")
    metrics.to_csv(output / "routing_per_class.csv", index=False)
    columns = [c for c in ("question_id", "run_id", "expected_route", "selected_route",
               "router_preferred_route", "router_confidence", "fallback_used", "actual_evidence_sources",
               "template_coverage_hit", "graph_retrieval_count", "vector_retrieval_count", "latency_s", "error") if c in frame]
    frame[columns].to_csv(output / "routing_per_question.csv", index=False)
    (output / "routing_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

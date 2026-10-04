"""
Regression check for the frozen 7-question pilot (Guide Section 10.2).

Asserts each system's result in a results directory against
data/benchmark/regression_expectations.json:

  - the system did not abstain ("Insufficient repository evidence.") on a
    question marked must_not_abstain;
  - the answer contains at least one of the expected answer entities;
  - latency stayed under the frozen ceiling;
  - any generated_cypher present still passes safe_read_cypher() (a
    logged-cypher re-check, independent of the generation-time check);
  - for adaptive_hybrid_graphrag / oracle_hybrid_rag only, the selected
    route matches the expected route (with the same code_retrieval /
    documentation_lookup leniency src/evaluation/metrics.py already
    applies) -- selected_retrieval_route is not a meaningful signal for
    the other systems.

Run after scripts/run_regression.ps1 has produced fresh result files:

    python -m src.evaluation.regression_check --results-dir results/regression
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from src.common import ROOT, read_jsonl, safe_read_cypher

ROUTE_CHECKED_SYSTEMS = {"adaptive_hybrid_graphrag", "oracle_hybrid_rag"}
ROUTE_LENIENT_CATEGORIES = {"code_retrieval", "documentation_lookup"}
ABSTENTION_TEXT = "insufficient repository evidence."
DEFAULT_EXPECTED_FAIL_SYSTEMS = {"plain_llm", "vector_rag"}


def normalize(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("\\", "/").split())


def answer_contains_entity(answer: str, entities: list[str]) -> bool:
    normalized_answer = normalize(answer)
    return any(normalize(entity) in normalized_answer for entity in entities)


def check_row(
    row: dict[str, Any], expectation: dict[str, Any], max_latency_s: float
) -> list[str]:
    failures: list[str] = []
    system = row.get("system", "")
    answer = str(row.get("answer", ""))

    if expectation.get("must_not_abstain") and normalize(answer) == ABSTENTION_TEXT:
        failures.append("abstained_when_answer_was_expected")

    expected_entities = expectation.get("expected_answer_entities", [])
    if expected_entities and not answer_contains_entity(answer, expected_entities):
        failures.append(f"answer_missing_expected_entity:{expected_entities}")

    latency = row.get("latency_s")
    if latency is not None:
        try:
            if float(latency) > max_latency_s:
                failures.append(f"latency_exceeded:{latency}s>{max_latency_s}s")
        except (TypeError, ValueError):
            pass

    cypher = row.get("generated_cypher")
    if cypher:
        try:
            safe_read_cypher(cypher)
        except ValueError as exc:
            failures.append(f"unsafe_cypher_logged:{exc}")

    if system in ROUTE_CHECKED_SYSTEMS:
        expected_route = expectation.get("expected_route")
        selected_route = row.get("selected_retrieval_route")
        category = expectation.get("category")

        if expected_route and selected_route:
            acceptable = {expected_route}

            if category in ROUTE_LENIENT_CATEGORIES:
                acceptable |= {"graph", "vector", "hybrid"}

            if selected_route not in acceptable:
                failures.append(
                    f"unexpected_route:got={selected_route!r},expected={sorted(acceptable)}"
                )

    return failures


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assert pilot results against frozen regression expectations."
    )
    parser.add_argument("--results-dir", default="results/regression")
    parser.add_argument(
        "--expectations", default="data/benchmark/regression_expectations.json"
    )
    parser.add_argument(
        "--expected-fail-systems",
        nargs="*",
        default=sorted(DEFAULT_EXPECTED_FAIL_SYSTEMS),
        help=(
            "Systems whose failed retrieval-quality expectations are "
            "intentional control outcomes."
        ),
    )
    args = parser.parse_args()

    expectations = json.loads((ROOT / args.expectations).read_text(encoding="utf-8"))
    expected_fail_systems = set(args.expected_fail_systems)
    max_latency_s = float(expectations.get("max_latency_s", 45.0))
    expectations_by_id = {q["id"]: q for q in expectations["questions"]}

    results_dir = ROOT / args.results_dir
    result_files = sorted(results_dir.glob("*_results.jsonl"))

    if not result_files:
        raise FileNotFoundError(f"No *_results.jsonl files found under {results_dir}")

    total_checks = 0
    total_failures = 0
    unexpected_failures = 0
    report_rows: list[dict[str, Any]] = []

    for path in result_files:
        for row in read_jsonl(path):
            question_id = str(row.get("question_id") or row.get("id") or "")
            expectation = expectations_by_id.get(question_id)

            if expectation is None:
                continue

            total_checks += 1
            system = str(row.get("system", ""))
            failures = check_row(row, expectation, max_latency_s)
            expected_failure = bool(failures) and system in expected_fail_systems
            status = (
                "PASS"
                if not failures
                else "EXPECTED_FAIL"
                if expected_failure
                else "FAIL"
            )

            if failures:
                total_failures += 1
                if not expected_failure:
                    unexpected_failures += 1

            report_rows.append(
                {
                    "system": row.get("system"),
                    "question_id": question_id,
                    "status": status,
                    "failures": failures,
                    "expected_failure": expected_failure,
                }
            )

            system_label = str(row.get("system", ""))
            print(
                f"[{status}] {system_label:28s} {question_id:25s} "
                f"{failures if failures else ''}"
            )

    report_path = ROOT / "results" / "regression_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report_rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print()
    print(
        f"Checked {total_checks} (system, question) pairs; "
        f"{total_failures} expectation failures, {unexpected_failures} unexpected."
    )
    print(f"Wrote report to: {report_path}")

    if unexpected_failures:
        sys.exit(1)


if __name__ == "__main__":
    main()

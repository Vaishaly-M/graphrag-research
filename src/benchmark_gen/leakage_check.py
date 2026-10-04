"""
No-context memorization / leakage check (Guide Section 6.1).

Runs Plain LLM (no retrieval, no repository context -- exactly the
existing plain_llm system) against benchmark questions with the
repository name masked, and flags any question the model still answers
correctly. A flagged question means the ground-truth fact may already be
present in the LLM's training data (a real risk here since 4 of the 5
source repositories -- apache/airflow, dotnet/eShop, mlflow/mlflow,
spring-projects/spring-petclinic -- are well-known open-source projects),
not that the benchmark item itself is wrong. It just means a correct
answer on that item cannot be attributed to retrieval.

This makes real Gemini API calls (one plain_llm call per question) and
should be run deliberately, not as part of routine testing.

Run:
    python -m src.benchmark_gen.leakage_check \
        --benchmark-file data/benchmark/splits/hidden_test_answer_key.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any

from src.common import ROOT, read_jsonl
from src.evaluation.metrics import coverage, expected_entities as gold_entities_for_row
from src.systems.plain_llm import System as PlainLLMSystem

REPO_MASK = "the target repository"


def mask_repository_name(question: str, repo: str) -> str:
    """
    Replace the repository slug (and its org/name fragments) with a
    generic placeholder. This cannot fully de-identify a question that
    also contains a unique file path, commit hash, or issue title -- that
    residual signal is exactly what a real memorization test should catch.
    """
    masked = question.replace(repo, REPO_MASK)

    org, _, name = repo.partition("/")
    if name:
        masked = re.sub(re.escape(name), REPO_MASK, masked, flags=re.I)

    return masked


def run_leakage_check(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    system = PlainLLMSystem()
    results: list[dict[str, Any]] = []

    for row in rows:
        if not row.get("answerable", True):
            # Unanswerable probes have no fact to memorize; skip them.
            continue

        repo = str(row.get("source_repo", ""))
        masked_question = mask_repository_name(str(row["question"]), repo)

        raw_answer = system.answer(masked_question)
        answer_text = (
            raw_answer["answer"] if isinstance(raw_answer, dict) else str(raw_answer)
        )

        expected = gold_entities_for_row(row)
        accuracy, coverage_value, matched, total = coverage(answer_text, expected)

        results.append(
            {
                "id": row.get("id"),
                "category": row.get("category"),
                "source_repo": repo,
                "masked_question": masked_question,
                "no_context_answer": answer_text,
                "expected_entities": expected,
                "matched_count": matched,
                "expected_count": total,
                "leaked_full_match": bool(accuracy),
                "leaked_partial_coverage": coverage_value,
            }
        )

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Flag benchmark questions a context-free LLM can already answer."
    )
    parser.add_argument(
        "--benchmark-file",
        default="data/benchmark/splits/hidden_test_answer_key.jsonl",
    )
    parser.add_argument(
        "--output", default="data/benchmark/splits/leakage_check_report.json"
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    benchmark_path = ROOT / args.benchmark_file
    rows = read_jsonl(benchmark_path)

    if not rows:
        raise FileNotFoundError(f"No benchmark rows found at {benchmark_path}")

    if args.limit:
        rows = rows[: args.limit]

    results = run_leakage_check(rows)

    flagged_full = [row for row in results if row["leaked_full_match"]]
    flagged_partial = [
        row
        for row in results
        if not row["leaked_full_match"]
        and row["leaked_partial_coverage"]
        and row["leaked_partial_coverage"] >= 0.5
    ]

    report = {
        "benchmark_file": str(benchmark_path),
        "total_checked": len(results),
        "flagged_full_match_count": len(flagged_full),
        "flagged_partial_coverage_count": len(flagged_partial),
        "flagged_full_match_ids": [row["id"] for row in flagged_full],
        "flagged_partial_coverage_ids": [row["id"] for row in flagged_partial],
        "results": results,
    }

    output_path = ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Checked {len(results)} questions for no-context memorization.")
    print(f"Fully leaked (exact-match without any retrieval): {len(flagged_full)}")
    print(
        "Partially leaked (>=50% entity coverage without retrieval): "
        f"{len(flagged_partial)}"
    )
    print(f"\nWrote report to: {output_path}")
    print(
        "\nWhen reporting results, compute a leakage-controlled subset by "
        "excluding flagged_full_match_ids (and optionally "
        "flagged_partial_coverage_ids) alongside the full-test-set numbers, "
        "per the guide's Section 6.1."
    )


if __name__ == "__main__":
    main()

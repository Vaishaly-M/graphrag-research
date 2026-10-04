from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = PROJECT_ROOT / "data" / "benchmark" / "benchmark_300.jsonl"
OUTPUT_FILE = PROJECT_ROOT / "data" / "benchmark" / "benchmark_pilot_7.jsonl"

REQUIRED_CATEGORIES = [
    "structure",
    "code_retrieval",
    "dependency_analysis",
    "documentation_lookup",
    "issue_pr_analysis",
    "developer_activity",
    "multi_hop",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Benchmark file not found: {path}")

    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_number} of {path}"
                ) from exc

            rows.append(row)

    return rows


def score_candidate(row: dict[str, Any]) -> tuple[int, int, int]:
    """
    Prefer questions that are suitable for a small system-validation pilot.

    Selection priorities:
    1. Questions with fewer ground-truth answers.
    2. Questions with complete structured evaluation metadata.
    3. Lower benchmark index for deterministic selection.
    """
    ground_truth = row.get("ground_truth", [])
    expected_entities = row.get("expected_entities", [])
    required_facts = row.get("required_facts", [])
    benchmark_index = int(row.get("benchmark_index", 999999))

    answer_count = len(ground_truth) if isinstance(ground_truth, list) else 999

    missing_metadata = 0

    if not expected_entities:
        missing_metadata += 1

    if not required_facts:
        missing_metadata += 1

    return answer_count, missing_metadata, benchmark_index


def select_pilot_questions(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        category = str(row.get("category", "")).strip()

        if category in REQUIRED_CATEGORIES:
            grouped[category].append(row)

    selected: list[dict[str, Any]] = []

    for category in REQUIRED_CATEGORIES:
        candidates = grouped.get(category, [])

        if not candidates:
            raise RuntimeError(
                f"No benchmark questions found for category: {category}"
            )

        candidates.sort(key=score_candidate)
        selected_row = dict(candidates[0])

        # Preserve the original benchmark ID and index.
        selected_row["pilot_index"] = len(selected) + 1
        selected.append(selected_row)

    return selected


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def print_summary(rows: list[dict[str, Any]]) -> None:
    print("\nPilot benchmark")
    print("-" * 80)

    for row in rows:
        ground_truth = row.get("ground_truth", [])

        print(
            f"{row['pilot_index']}. "
            f"{row.get('category', 'unknown'):24s} "
            f"ID={row.get('id', 'unknown'):25s} "
            f"answers={len(ground_truth)}"
        )
        print(f"   {row.get('question', '')}")

    print("-" * 80)
    print(f"Total pilot questions: {len(rows)}")


def main() -> None:
    rows = read_jsonl(INPUT_FILE)
    selected = select_pilot_questions(rows)
    write_jsonl(OUTPUT_FILE, selected)
    print_summary(selected)
    print(f"\nWrote pilot benchmark to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
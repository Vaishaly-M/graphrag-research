from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from src.common import (
    ROOT,
    append_jsonl,
    completed_ids,
    read_jsonl,
    write_jsonl,
)


DEFAULT_PILOT_BENCHMARK = Path(
    "data/benchmark/benchmark_pilot_7.csv"
)

DEFAULT_PILOT_OUTPUT_DIR = Path(
    "results/pilot_raw"
)


STRUCTURED_COLUMNS = {
    "retrieved_evidence",
    "predicted_relations",
    "predicted_path",
    "generated_cypher",
    "retrieval_errors",
    "adaptive_plan",
    "graph_results",
    "vector_results",
    "routing_metadata",
}


def add_run_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    """Add shared command-line arguments for every system."""

    parser.add_argument(
        "--benchmark-file",
        type=Path,
        default=DEFAULT_PILOT_BENCHMARK,
        help=(
            "Benchmark file to execute. "
            "Both CSV and JSONL are supported."
        ),
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_PILOT_OUTPUT_DIR,
        help="Directory in which result files will be written.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of benchmark questions.",
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing result files before execution.",
    )

    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help=(
            "Run each question this many times (Guide Section 15.2), "
            "e.g. to measure variance under nondeterministic generation. "
            "Each repeat is tagged with run_id and a composite run_key so "
            "resumption never confuses one repeat for another."
        ),
    )


class BaseSystem:
    """Shared benchmark runner used by all QA systems."""

    name = "base"

    def answer(
        self,
        question: str,
    ) -> str | dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def _resolve_path(
        path: str | Path,
    ) -> Path:
        resolved = Path(path)

        if resolved.is_absolute():
            return resolved

        return ROOT / resolved

    @staticmethod
    def _normalise_result(
        result: str | dict[str, Any],
    ) -> dict[str, Any]:
        """
        Convert an answer into a standard result dictionary.
        """
        if isinstance(result, dict):
            normalised = dict(result)
            normalised.setdefault("answer", "")
            return normalised

        return {
            "answer": str(result),
        }

    @staticmethod
    def _load_benchmark(
        benchmark_path: Path,
    ) -> list[dict[str, Any]]:
        """
        Load a benchmark from CSV or JSONL.
        """
        suffix = benchmark_path.suffix.lower()

        if suffix == ".jsonl":
            rows = read_jsonl(benchmark_path)

        elif suffix == ".csv":
            dataframe = pd.read_csv(
                benchmark_path,
                encoding="utf-8",
            )

            # Replace pandas NaN values with None so JSON output is valid.
            dataframe = dataframe.where(
                pd.notna(dataframe),
                None,
            )

            rows = dataframe.to_dict(
                orient="records",
            )

        else:
            raise ValueError(
                "Unsupported benchmark format: "
                f"{benchmark_path.suffix}. "
                "Use a .csv or .jsonl benchmark file."
            )

        BaseSystem._validate_benchmark_rows(
            rows,
            benchmark_path,
        )

        return rows

    @staticmethod
    def _validate_benchmark_rows(
        rows: list[dict[str, Any]],
        benchmark_path: Path,
    ) -> None:
        """
        Confirm that the benchmark contains the required columns.
        """
        if not rows:
            raise ValueError(
                f"Benchmark file contains no questions: "
                f"{benchmark_path}"
            )

        for index, row in enumerate(rows, start=1):
            if "question" not in row:
                raise ValueError(
                    f"Benchmark row {index} has no "
                    f"'question' field."
                )

            if row.get("question") is None:
                raise ValueError(
                    f"Benchmark row {index} has an empty "
                    f"'question' field."
                )

            # Accept either id or question_id.
            if (
                row.get("id") is None
                and row.get("question_id") is None
            ):
                # Assign a stable fallback ID.
                row["id"] = f"question_{index:04d}"

    @staticmethod
    def _serialise_csv_value(
        value: Any,
    ) -> Any:
        """
        Convert nested structures into valid JSON strings for CSV output.
        """
        if isinstance(
            value,
            (
                dict,
                list,
                tuple,
                set,
            ),
        ):
            return json.dumps(
                value,
                ensure_ascii=False,
                default=str,
            )

        return value

    @classmethod
    def _export_csv(
        cls,
        jsonl_path: Path,
        csv_path: Path,
    ) -> None:
        """
        Export result JSONL rows to a CSV file.
        """
        rows = read_jsonl(jsonl_path)

        if not rows:
            print(
                f"No rows available for CSV export: "
                f"{jsonl_path}"
            )
            return

        csv_rows: list[dict[str, Any]] = []

        for row in rows:
            csv_row: dict[str, Any] = {}

            for key, value in row.items():
                if (
                    key in STRUCTURED_COLUMNS
                    or isinstance(
                        value,
                        (
                            dict,
                            list,
                            tuple,
                            set,
                        ),
                    )
                ):
                    csv_row[key] = cls._serialise_csv_value(
                        value
                    )
                else:
                    csv_row[key] = value

            csv_rows.append(csv_row)

        dataframe = pd.DataFrame(csv_rows)

        dataframe.to_csv(
            csv_path,
            index=False,
            encoding="utf-8-sig",
        )

    def run(
        self,
        benchmark: str | Path = DEFAULT_PILOT_BENCHMARK,
        output_dir: str | Path = DEFAULT_PILOT_OUTPUT_DIR,
        limit: int | None = None,
        reset: bool = False,
        repeats: int = 1,
    ) -> None:
        if repeats <= 0:
            raise ValueError("--repeats must be greater than zero.")
        benchmark_path = self._resolve_path(
            benchmark
        )

        output_directory = self._resolve_path(
            output_dir
        )

        if not benchmark_path.exists():
            raise FileNotFoundError(
                f"Benchmark file not found: "
                f"{benchmark_path}"
            )

        if limit is not None and limit <= 0:
            raise ValueError(
                "--limit must be greater than zero."
            )

        output_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        jsonl_output = (
            output_directory
            / f"{self.name}_results.jsonl"
        )

        csv_output = (
            output_directory
            / f"{self.name}_results.csv"
        )

        if reset:
            jsonl_output.unlink(
                missing_ok=True
            )

            csv_output.unlink(
                missing_ok=True
            )

        rows = self._load_benchmark(
            benchmark_path
        )

        if limit is not None:
            rows = rows[:limit]

        # Errors are not completed experiment results. Previously, a
        # temporary quota/network error was added to ``done`` and could
        # never recover without resetting the whole run. Retain successful
        # rows and retry failed run keys on the next invocation.
        existing_rows = read_jsonl(jsonl_output)
        retained_rows = [
            row for row in existing_rows
            if not row.get("error")
        ]

        if len(retained_rows) != len(existing_rows):
            write_jsonl(jsonl_output, retained_rows)
            print(
                "Removed "
                f"{len(existing_rows) - len(retained_rows)} failed "
                "row(s) so they will be retried."
            )

        done = completed_ids(jsonl_output)

        total_iterations = len(rows) * repeats

        print()
        print("System execution")
        print("-" * 80)
        print(f"System        : {self.name}")
        print(f"Benchmark     : {benchmark_path}")
        print(f"Questions     : {len(rows)}")
        print(f"Repeats       : {repeats}")
        print(f"Total runs    : {total_iterations}")
        print(f"Completed IDs : {len(done)}")
        print(f"JSONL output  : {jsonl_output}")
        print(f"CSV output    : {csv_output}")
        print("-" * 80)

        processed_now = 0
        skipped = 0
        failed = 0
        iteration = 0

        for repeat_index in range(1, repeats + 1):
            for row in rows:
                iteration += 1

                identifier = row.get(
                    "question_id"
                )

                if identifier is None:
                    identifier = row.get(
                        "id"
                    )

                question_id = str(identifier)

                # A single-repeat run keys resumption on question_id alone,
                # exactly matching every existing result file's format.
                # Multi-repeat runs need a composite key so repeat 2 is not
                # mistaken for an already-completed repeat 1.
                run_key = (
                    question_id
                    if repeats == 1
                    else f"{question_id}::run{repeat_index}"
                )

                if run_key in done:
                    print(
                        f"[{iteration}/{total_iterations}] "
                        f"Skipping completed run: "
                        f"{run_key}"
                    )

                    skipped += 1
                    continue

                question = str(
                    row["question"]
                ).strip()

                start = time.perf_counter()

                try:
                    raw_result = self.answer(
                        question
                    )

                    result_data = (
                        self._normalise_result(
                            raw_result
                        )
                    )

                    error: str | None = None

                except Exception as exc:
                    result_data = {
                        "answer": "",
                    }

                    error = (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )

                    failed += 1

                latency = (
                    time.perf_counter()
                    - start
                )

                output_row = {
                    **row,
                    "question_id": question_id,
                    "run_id": repeat_index,
                    "run_key": run_key,
                    "system": self.name,
                    **result_data,
                    "latency_s": round(
                        latency,
                        6,
                    ),
                    "error": error,
                }

                append_jsonl(
                    jsonl_output,
                    output_row,
                )

                processed_now += 1
                done.add(run_key)

                status = (
                    "ERROR"
                    if error
                    else "OK"
                )

                print(
                    f"[{iteration}/{total_iterations}] "
                    f"{status:5s} "
                    f"{run_key} "
                    f"({latency:.2f}s)"
                )

                if error:
                    print(
                        f"          {error}"
                    )

        self._export_csv(
            jsonl_output,
            csv_output,
        )

        print()
        print("Execution completed")
        print("-" * 80)
        print(
            f"Processed : {processed_now}"
        )
        print(
            f"Skipped   : {skipped}"
        )
        print(
            f"Failed    : {failed}"
        )
        print(
            f"JSONL file: "
            f"{jsonl_output.resolve()}"
        )
        print(
            f"CSV file  : "
            f"{csv_output.resolve()}"
        )

"""
Generate the thesis result tables (Guide Section 19) directly from
per_question_metrics.csv, so every reported number traces back to a
specific evaluation run rather than being retyped by hand.

Produces five CSVs:
  1. main_performance.csv       -- one row per system, overall
  2. category_breakdown.csv     -- one row per system, one column per
                                    benchmark category
  3. reasoning_depth_breakdown.csv -- one row per system, one column per
                                    reasoning_hops bucket (0/1/2/3+)
  4. ablation_table.csv         -- one row per ablation variant, if
                                    --ablations-dir is given and populated
  5. failure_analysis.csv       -- one row per failure type, one column
                                    per system

Run:
    python -m src.evaluation.report_tables \
        --per-question results/per_question_metrics.csv \
        --output-dir results/report_tables \
        --ablations-dir results/ablations
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from src.common import ROOT

CATEGORY_ORDER = [
    "structure",
    "code_retrieval",
    "dependency_analysis",
    "documentation_lookup",
    "issue_pr_analysis",
    "developer_activity",
    "multi_hop",
]

DEPTH_BUCKETS = ["zero_hop", "one_hop", "two_hop", "three_plus_hop"]


def depth_bucket(hops: Any) -> str:
    value = pd.to_numeric(hops, errors="coerce")

    if pd.isna(value):
        return "unknown"

    value = int(value)

    if value <= 0:
        return "zero_hop"
    if value == 1:
        return "one_hop"
    if value == 2:
        return "two_hop"

    return "three_plus_hop"


def load_per_question(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)

    if "system" not in frame.columns:
        raise ValueError(f"{path} has no 'system' column")

    return frame


def main_performance_table(frame: pd.DataFrame, k: int) -> pd.DataFrame:
    recall_column = f"evidence_recall_at_{k}"
    rows: list[dict[str, Any]] = []

    for system, group in frame.groupby("system", sort=True):
        rows.append(
            {
                "system": system,
                "accuracy": group["answer_accuracy"].mean(),
                "entity_f1": group["entity_f1"].mean()
                if "entity_f1" in group
                else float("nan"),
                "retrieval_recall": group[recall_column].mean()
                if recall_column in group
                else float("nan"),
                "faithfulness": group["supported_claim_rate"].mean()
                if "supported_claim_rate" in group
                else float("nan"),
                "hallucination_rate": group["hallucination_rate"].mean()
                if "hallucination_rate" in group
                else float("nan"),
                "answer_coverage": (
                    1 - group["abstained"].mean()
                    if "abstained" in group
                    else float("nan")
                ),
                "median_latency_s": group["latency_s"].median()
                if "latency_s" in group
                else float("nan"),
                "mean_token_usage": group["token_usage"].mean()
                if "token_usage" in group
                else float("nan"),
                "n": len(group),
            }
        )

    result = pd.DataFrame(rows)

    if result["mean_token_usage"].isna().all():
        print(
            "Note: token_usage is not populated by any system "
            "(GeminiClient does not currently expose usage from the "
            "API response) -- mean_token_usage is NaN for every system, "
            "not zero cost."
        )

    return result


def category_breakdown_table(
    frame: pd.DataFrame, metric: str
) -> pd.DataFrame:
    if metric not in frame.columns or "category" not in frame.columns:
        return pd.DataFrame()

    pivot = frame.pivot_table(
        index="system", columns="category", values=metric, aggfunc="mean"
    )

    ordered_columns = [c for c in CATEGORY_ORDER if c in pivot.columns]
    ordered_columns += [c for c in pivot.columns if c not in ordered_columns]

    return pivot[ordered_columns].reset_index()


def reasoning_depth_table(frame: pd.DataFrame, metric: str) -> pd.DataFrame:
    if metric not in frame.columns or "reasoning_hops" not in frame.columns:
        return pd.DataFrame()

    working = frame.copy()
    working["depth_bucket"] = working["reasoning_hops"].apply(depth_bucket)

    pivot = working.pivot_table(
        index="system", columns="depth_bucket", values=metric, aggfunc="mean"
    )

    ordered_columns = [c for c in DEPTH_BUCKETS if c in pivot.columns]
    ordered_columns += [c for c in pivot.columns if c not in ordered_columns]

    return pivot[ordered_columns].reset_index()


def ablation_table(ablations_dir: Path) -> pd.DataFrame:
    if not ablations_dir.exists():
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []

    for variant_dir in sorted(ablations_dir.iterdir()):
        summary_path = variant_dir / "evaluation" / "summary_metrics.csv"

        if not summary_path.exists():
            continue

        summary = pd.read_csv(summary_path)
        adaptive_row = summary[summary["system"] == "adaptive_hybrid_graphrag"]

        if adaptive_row.empty:
            continue

        adaptive_row = adaptive_row.iloc[0]

        rows.append(
            {
                "variant": variant_dir.name,
                "accuracy": adaptive_row.get("answer_accuracy"),
                "entity_f1": adaptive_row.get("entity_f1"),
                "faithfulness": adaptive_row.get("supported_claim_rate"),
                "hallucination_rate": adaptive_row.get("hallucination_rate"),
                "latency_s": adaptive_row.get("latency_s"),
            }
        )

    return pd.DataFrame(rows)


def failure_analysis_table(frame: pd.DataFrame) -> pd.DataFrame:
    failure_definitions = {
        "wrong_route": (
            "retrieval_route_accuracy",
            lambda series: 1 - series.mean(),
        ),
        "empty_retrieval": (
            "graph_query_empty_result",
            lambda series: series.mean(),
        ),
        "invalid_query": (
            "graph_query_invalid",
            lambda series: series.mean(),
        ),
        "missing_entities": (
            "entity_recall",
            lambda series: (series < 1).mean(),
        ),
        "unsupported_claim": (
            "hallucination_rate",
            lambda series: series.mean(),
        ),
        "unnecessary_abstention": (
            "abstention_quality",
            lambda series: (series == "unnecessary_abstention").mean(),
        ),
    }

    systems = sorted(frame["system"].unique())
    rows: list[dict[str, Any]] = []

    for failure_type, (column, aggregate) in failure_definitions.items():
        row: dict[str, Any] = {"failure_type": failure_type}

        for system in systems:
            group = frame[frame["system"] == system]

            if column not in group.columns or group[column].dropna().empty:
                row[system] = float("nan")
                continue

            row[system] = aggregate(group[column].dropna())

        rows.append(row)

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the thesis result tables from per_question_metrics.csv."
    )
    parser.add_argument(
        "--per-question", default="results/per_question_metrics.csv"
    )
    parser.add_argument("--output-dir", default="results/report_tables")
    parser.add_argument("--ablations-dir", default="results/ablations")
    parser.add_argument("--retrieval-k", type=int, default=10)
    parser.add_argument(
        "--category-metric",
        default="answer_accuracy",
        help="Metric shown in category_breakdown.csv.",
    )
    parser.add_argument(
        "--depth-metric",
        default="answer_accuracy",
        help="Metric shown in reasoning_depth_breakdown.csv.",
    )
    args = parser.parse_args()

    frame = load_per_question(ROOT / args.per_question)
    output_dir = ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    tables = {
        "main_performance.csv": main_performance_table(frame, args.retrieval_k),
        "category_breakdown.csv": category_breakdown_table(
            frame, args.category_metric
        ),
        "reasoning_depth_breakdown.csv": reasoning_depth_table(
            frame, args.depth_metric
        ),
        "ablation_table.csv": ablation_table(ROOT / args.ablations_dir),
        "failure_analysis.csv": failure_analysis_table(frame),
    }

    for filename, table in tables.items():
        path = output_dir / filename

        if table.empty:
            print(f"Skipped {filename} (no data available for this table).")
            continue

        table.to_csv(path, index=False)
        print(f"Wrote {filename} ({len(table)} rows) to: {path}")

    print(f"\nAll tables written under: {output_dir}")


if __name__ == "__main__":
    main()

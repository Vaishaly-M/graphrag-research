"""
Pairwise statistical comparison between systems (Guide Section 17).

For each metric, and for "overall" plus every requested subgroup (e.g.
per-category, per-difficulty), runs on the paired per-question values:
  - the Wilcoxon signed-rank test (matching the original script's
    zero-difference handling);
  - a paired bootstrap confidence interval on the mean difference;
  - rank-biserial effect size;
  - Holm's step-down correction across the family of pairwise comparisons
    within that metric+subgroup, so a large comparison matrix doesn't
    inflate false positives.

The question is the unit of analysis (Guide Section 17.1): every pairing
is done on shared question_id values only.

Run:
    python -m src.evaluation.statistics \
        --input results/per_question_metrics.csv \
        --output-dir results
"""

from __future__ import annotations

import argparse
import itertools
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

from src.common import ROOT

DEFAULT_METRICS = [
    "answer_accuracy",
    "entity_f1",
    "required_fact_coverage",
    "hallucination_rate",
    "token_f1",
    "rouge_l",
    "evidence_recall_at_10",
    "latency_s",
]

DEFAULT_SUBGROUP_COLUMNS = ["category", "difficulty_level"]

BOOTSTRAP_ITERATIONS = 2000
BOOTSTRAP_SEED = 42


def paired_bootstrap_ci(
    diff: np.ndarray,
    iterations: int,
    seed: int,
    confidence: float = 0.95,
) -> tuple[float, float, float]:
    """Percentile bootstrap CI on the mean of paired differences."""
    if len(diff) == 0:
        return float("nan"), float("nan"), float("nan")

    rng = np.random.default_rng(seed)
    n = len(diff)
    means = np.empty(iterations)

    for i in range(iterations):
        sample = rng.choice(diff, size=n, replace=True)
        means[i] = sample.mean()

    lower_q = (1 - confidence) / 2
    upper_q = 1 - lower_q

    return (
        float(diff.mean()),
        float(np.quantile(means, lower_q)),
        float(np.quantile(means, upper_q)),
    )


def rank_biserial(diff: pd.Series) -> float:
    nonzero = diff[diff != 0]

    if len(nonzero) == 0:
        return 0.0

    ranks = nonzero.abs().rank()

    return float(
        (ranks[nonzero > 0].sum() - ranks[nonzero < 0].sum()) / ranks.sum()
    )


def wilcoxon_pair(x: pd.Series, y: pd.Series) -> tuple[float, float]:
    diff = x - y
    nonzero = diff[diff != 0]

    if len(nonzero) == 0:
        return 0.0, 1.0

    stat, p_value = wilcoxon(x, y, zero_method="wilcox")
    return float(stat), float(p_value)


def holm_correction(p_values: list[float]) -> list[float]:
    """
    Holm's step-down correction. Returns adjusted p-values in the same
    order as the input list.
    """
    m = len(p_values)

    if m == 0:
        return []

    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running_max = 0.0

    for rank, index in enumerate(order):
        adjusted_value = (m - rank) * p_values[index]
        running_max = max(running_max, adjusted_value)
        adjusted[index] = min(running_max, 1.0)

    return adjusted


def compare_systems(
    frame: pd.DataFrame,
    metric: str,
    id_column: str,
) -> list[dict[str, Any]]:
    if metric not in frame.columns or "system" not in frame.columns:
        return []

    pivot = frame.pivot_table(
        index=id_column, columns="system", values=metric, aggfunc="mean"
    )
    systems = list(pivot.columns)
    rows: list[dict[str, Any]] = []

    for system_a, system_b in itertools.combinations(systems, 2):
        paired = pivot[[system_a, system_b]].dropna()

        if paired.empty:
            continue

        diff = (paired[system_a] - paired[system_b]).to_numpy()
        stat, p_value = wilcoxon_pair(paired[system_a], paired[system_b])
        mean_diff, ci_low, ci_high = paired_bootstrap_ci(
            diff, BOOTSTRAP_ITERATIONS, BOOTSTRAP_SEED
        )
        rbc = rank_biserial(paired[system_a] - paired[system_b])

        rows.append(
            {
                "metric": metric,
                "system_a": system_a,
                "system_b": system_b,
                "n": len(paired),
                "mean_a": float(paired[system_a].mean()),
                "mean_b": float(paired[system_b].mean()),
                "mean_diff": mean_diff,
                "ci95_low": ci_low,
                "ci95_high": ci_high,
                "wilcoxon_w": stat,
                "p_value": p_value,
                "rank_biserial": rbc,
            }
        )

    p_values = [row["p_value"] for row in rows]

    for row, adjusted_p in zip(rows, holm_correction(p_values)):
        row["p_value_holm"] = adjusted_p

    return rows


def run_all_comparisons(
    frame: pd.DataFrame,
    metrics: list[str],
    id_column: str,
    subgroup_columns: list[str],
) -> pd.DataFrame:
    all_rows: list[dict[str, Any]] = []

    for metric in metrics:
        overall_rows = compare_systems(frame, metric, id_column)

        for row in overall_rows:
            row["subgroup_column"] = "overall"
            row["subgroup_value"] = "overall"

        all_rows.extend(overall_rows)

        for subgroup_column in subgroup_columns:
            if subgroup_column not in frame.columns:
                continue

            for subgroup_value, group in frame.groupby(subgroup_column):
                subgroup_rows = compare_systems(group, metric, id_column)

                for row in subgroup_rows:
                    row["subgroup_column"] = subgroup_column
                    row["subgroup_value"] = str(subgroup_value)

                all_rows.extend(subgroup_rows)

    return pd.DataFrame(all_rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pairwise statistical comparison between systems."
    )
    parser.add_argument("--input", default="results/per_question_metrics.csv")
    parser.add_argument("--output-dir", default="results")
    parser.add_argument("--metrics", nargs="+", default=None)
    parser.add_argument("--id-column", default="question_id")
    parser.add_argument(
        "--subgroup-columns", nargs="+", default=DEFAULT_SUBGROUP_COLUMNS
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    input_path = ROOT / args.input
    frame = pd.read_csv(input_path)

    if args.id_column not in frame.columns:
        raise ValueError(
            f"{input_path} has no '{args.id_column}' column"
        )

    metrics = args.metrics or [
        metric for metric in DEFAULT_METRICS if metric in frame.columns
    ]

    if not metrics:
        raise ValueError(
            "None of the requested metric columns were found in "
            f"{input_path}."
        )

    result = run_all_comparisons(
        frame, metrics, args.id_column, args.subgroup_columns
    )

    output_path = ROOT / args.output_dir / "statistical_tests.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)

    print(f"Wrote {len(result)} pairwise comparisons to: {output_path}")

    if result.empty:
        print("No comparisons were produced (check --metrics/--id-column).")
        return

    overall = result[result["subgroup_column"] == "overall"]

    with pd.option_context(
        "display.max_columns", None, "display.width", 220,
        "display.float_format", lambda value: f"{value:.4f}",
    ):
        print("\nOverall comparisons")
        print("-" * 100)
        print(overall.to_string(index=False))

    print(
        "\nSubgroup comparisons (per category/difficulty, etc.) are in "
        f"{output_path} but not printed here -- filter by subgroup_column."
    )


if __name__ == "__main__":
    main()

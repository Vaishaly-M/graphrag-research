"""
Inter-annotator agreement for the blinded hallucination sheet (Guide
Section 13.3).

Expects two or more completed copies of the sheet produced by
hallucination_annotation.py, each filled in independently by one
annotator and saved under a distinct filename. Computes Cohen's kappa for
exactly two annotators and Krippendorff's alpha (nominal, missing-value
tolerant) for any number of annotators, per label column.

Run:
    python -m src.evaluation.agreement \
        --sheets results/annotator_a.csv results/annotator_b.csv
"""

from __future__ import annotations

import argparse
from itertools import combinations

import pandas as pd

DEFAULT_LABELS = (
    "supported",
    "unsupported",
    "contradicted",
    "incomplete",
    "irrelevant",
    "failure_source",
)


def cohens_kappa(a: pd.Series, b: pd.Series) -> float:
    """Unweighted Cohen's kappa for two annotators' labels on the same items."""
    paired = pd.DataFrame({"a": a, "b": b}).dropna()

    if paired.empty:
        return float("nan")

    observed_agreement = (paired["a"] == paired["b"]).mean()

    categories = sorted(set(paired["a"]) | set(paired["b"]))
    expected_agreement = sum(
        (paired["a"] == category).mean() * (paired["b"] == category).mean()
        for category in categories
    )

    denominator = 1 - expected_agreement

    if denominator == 0:
        return 1.0 if observed_agreement == 1.0 else float("nan")

    return (observed_agreement - expected_agreement) / denominator


def krippendorff_alpha_nominal(rows: list[list[str | None]]) -> float:
    """
    Krippendorff's alpha for nominal data with missing values.

    `rows` is one list per item, containing each annotator's label for
    that item (None where an annotator did not label it).
    """
    pairs: list[tuple[str, str]] = []

    for item_labels in rows:
        present = [label for label in item_labels if label is not None]

        for a, b in combinations(present, 2):
            pairs.append((a, b))
            pairs.append((b, a))

    if not pairs:
        return float("nan")

    all_labels = [label for pair in pairs for label in pair]
    categories = sorted(set(all_labels))
    counts = {category: all_labels.count(category) for category in categories}
    total = len(all_labels)

    if total <= 1:
        return float("nan")

    observed_disagreement = sum(
        0.0 if a == b else 1.0 for a, b in pairs
    ) / len(pairs)

    expected_disagreement = 0.0
    for a in categories:
        for b in categories:
            if a == b:
                continue
            expected_disagreement += counts[a] * counts[b]

    expected_disagreement /= total * (total - 1)

    if expected_disagreement == 0:
        return 1.0 if observed_disagreement == 0 else float("nan")

    return 1 - (observed_disagreement / expected_disagreement)


def load_sheet(path: str, id_column: str) -> pd.DataFrame:
    frame = pd.read_csv(path)

    if id_column not in frame.columns:
        raise ValueError(f"{path} has no '{id_column}' column")

    return frame.set_index(id_column)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute inter-annotator agreement on hallucination sheets."
    )
    parser.add_argument("--sheets", nargs="+", required=True)
    parser.add_argument("--labels", nargs="+", default=list(DEFAULT_LABELS))
    parser.add_argument("--id-column", default="annotation_id")
    args = parser.parse_args()

    frames = [load_sheet(path, args.id_column) for path in args.sheets]

    common_ids = set(frames[0].index)
    for frame in frames[1:]:
        common_ids &= set(frame.index)

    common_ids = sorted(common_ids)

    if not common_ids:
        raise ValueError(
            "The provided sheets have no overlapping "
            f"'{args.id_column}' values."
        )

    print(
        f"Comparing {len(frames)} annotators over {len(common_ids)} "
        "shared items.\n"
    )

    for label in args.labels:
        print(f"Label: {label}")

        if len(frames) == 2:
            a = (
                frames[0].loc[common_ids, label]
                if label in frames[0].columns
                else pd.Series(dtype=object)
            )
            b = (
                frames[1].loc[common_ids, label]
                if label in frames[1].columns
                else pd.Series(dtype=object)
            )
            kappa = cohens_kappa(a, b)
            print(
                f"  Cohen's kappa: {kappa:.4f}"
                if kappa == kappa
                else "  Cohen's kappa: n/a"
            )

        rows: list[list[str | None]] = []

        for item_id in common_ids:
            item_labels: list[str | None] = []

            for frame in frames:
                if label in frame.columns:
                    value = frame.loc[item_id, label]
                    item_labels.append(
                        str(value).strip()
                        if pd.notna(value) and str(value).strip()
                        else None
                    )
                else:
                    item_labels.append(None)

            rows.append(item_labels)

        alpha = krippendorff_alpha_nominal(rows)
        print(
            f"  Krippendorff's alpha: {alpha:.4f}"
            if alpha == alpha
            else "  Krippendorff's alpha: n/a"
        )
        print()


if __name__ == "__main__":
    main()

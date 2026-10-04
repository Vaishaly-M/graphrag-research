"""
Blinded hallucination/failure annotation sheet (Guide Section 13).

Unlike the original hallucination_template.py, this hides the system name
from annotators and shuffles row order with a fixed seed, so an annotator
cannot infer which system produced an answer from file order or an
explicit column. The system/question mapping is written to a separate key
file annotators should never see; join it back only after annotation is
complete.

Run:
    python -m src.evaluation.hallucination_annotation --results-dir results/regression
"""

from __future__ import annotations

import argparse
import json
import random

import pandas as pd

from src.common import ROOT, config_get, read_jsonl

BLIND_SEED = int(config_get("seeds.benchmark_generation", 42))

ANNOTATION_LABELS = (
    "supported",
    "unsupported",
    "contradicted",
    "incomplete",
    "irrelevant",
)

FAILURE_SOURCES = (
    "none",
    "retrieval_failure",
    "graph_reasoning_failure",
    "vector_retrieval_failure",
    "routing_failure",
    "answer_generation_failure",
    "evidence_validation_failure",
    "abstention_failure",
)


def load_source_rows(
    results_dir,
    answer_key: dict[str, str] | None = None,
) -> list[dict]:
    source_rows: list[dict] = []

    for path in sorted(results_dir.glob("*_results.jsonl")):
        for record in read_jsonl(path):
            question_id = str(record.get("question_id", record.get("id", "")))
            ground_truth = record.get(
                "ground_truth",
                record.get("expected_answer", answer_key.get(question_id, "") if answer_key else ""),
            )

            if isinstance(ground_truth, list):
                ground_truth_text = " | ".join(
                    str(item) for item in ground_truth
                )
            else:
                ground_truth_text = str(ground_truth or "")

            source_rows.append(
                {
                    "system": record.get("system", path.stem),
                    "question_id": question_id,
                    "question": record.get("question", ""),
                    "ground_truth": ground_truth_text,
                    "answer": record.get("answer", ""),
                }
            )

    return source_rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a blinded hallucination/failure annotation sheet."
    )
    parser.add_argument("--results-dir", default="results")
    parser.add_argument(
        "--answer-key",
        default=None,
        help="Optional CSV answer key used to supply gold answers omitted from hidden-test inputs.",
    )
    parser.add_argument(
        "--output", default="results/hallucination_annotation.csv"
    )
    parser.add_argument(
        "--key-output", default="results/hallucination_annotation_key.json"
    )
    args = parser.parse_args()

    answer_key: dict[str, str] = {}
    if args.answer_key:
        key_frame = pd.read_csv(ROOT / args.answer_key)
        key_id_column = "question_id" if "question_id" in key_frame else "id"
        if key_id_column not in key_frame or "expected_answer" not in key_frame:
            raise ValueError("Answer key must contain an id/question_id and expected_answer column.")
        answer_key = {
            str(row[key_id_column]): str(row["expected_answer"] or "")
            for _, row in key_frame.iterrows()
        }

    source_rows = load_source_rows(ROOT / args.results_dir, answer_key)

    if not source_rows:
        raise FileNotFoundError(
            f"No *_results.jsonl files found under {ROOT / args.results_dir}"
        )

    rng = random.Random(BLIND_SEED)
    rng.shuffle(source_rows)

    key: dict[str, dict[str, str]] = {}
    annotation_rows: list[dict] = []

    for index, row in enumerate(source_rows, start=1):
        annotation_id = f"A{index:04d}"

        key[annotation_id] = {
            "system": row["system"],
            "question_id": str(row["question_id"]),
        }

        annotation_row = {
            "annotation_id": annotation_id,
            "question": row["question"],
            "ground_truth": row["ground_truth"],
            "answer": row["answer"],
        }

        for label in ANNOTATION_LABELS:
            annotation_row[label] = ""

        annotation_row["failure_source"] = ""
        annotation_row["annotator_notes"] = ""

        annotation_rows.append(annotation_row)

    output_path = ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(annotation_rows).to_csv(output_path, index=False)

    key_path = ROOT / args.key_output
    key_path.write_text(
        json.dumps(key, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Wrote {len(annotation_rows)} blinded rows to: {output_path}")
    print(
        "Wrote the (PRIVATE -- do not share with annotators) system key "
        f"to: {key_path}"
    )
    print(f"\nAnnotation labels (Guide Section 13.2): {ANNOTATION_LABELS}")
    print(f"Failure sources (Guide Section 13.2): {FAILURE_SOURCES}")
    print(
        "\nAnnotators should see only the CSV above, not the key file. "
        "Have at least two annotators complete independent copies (save "
        "each under a distinct filename), then use "
        "src/evaluation/agreement.py before joining results back to the "
        "key file."
    )


if __name__ == "__main__":
    main()

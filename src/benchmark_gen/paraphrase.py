"""
Generate paraphrases of benchmark questions for leakage/robustness testing
(Guide Section 6.2). Uses Ollama only -- consistent with this project's
existing rule (see README) that Ollama touches non-measured input text,
never a measured system output.

Paraphrases are written to a side file and are NOT merged into the frozen
benchmark rows. They are flagged for manual review before use: a
paraphrase that subtly changes the intended answer (e.g. rewording a
filter so a different set of entities now qualifies) would silently
corrupt the benchmark's ground truth, so nothing here is auto-accepted.

Run:
    python -m src.benchmark_gen.paraphrase \
        --input data/benchmark/splits/hidden_test_answer_key.jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
from typing import Any

from src.common import ROOT, read_jsonl
from src.synthetic_gen.generate import generate_with_ollama, validate_ollama

PARAPHRASE_COUNT = 2

PROMPT_TEMPLATE = """Rewrite the following repository question in a different phrasing.
Keep the exact same intended answer -- do not broaden, narrow, or change
which entities the question refers to. Preserve every identifier exactly:
repository names, file paths, commit hashes, issue numbers, directory
names, and quoted text fragments must appear unchanged.

Do not answer the question. Output only the rewritten question, with no
explanation, numbering, or quotation marks around it.

Original question:
{question}
"""


def generate_paraphrases(question: str, count: int) -> list[str]:
    paraphrases: list[str] = []

    for _ in range(count):
        try:
            paraphrase = generate_with_ollama(
                PROMPT_TEMPLATE.format(question=question)
            )
        except Exception as error:
            paraphrase = (
                f"[paraphrase_generation_failed: {type(error).__name__}: {error}]"
            )

        paraphrases.append(paraphrase)

    return paraphrases


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate manual-review paraphrases of benchmark questions."
    )
    parser.add_argument(
        "--input", default="data/benchmark/splits/hidden_test_answer_key.jsonl"
    )
    parser.add_argument("--output", default="data/benchmark/paraphrases.jsonl")
    parser.add_argument(
        "--review-csv", default="data/benchmark/paraphrases_review.csv"
    )
    parser.add_argument("--count", type=int, default=PARAPHRASE_COUNT)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    validate_ollama()

    input_path = ROOT / args.input
    rows = read_jsonl(input_path)

    if not rows:
        raise FileNotFoundError(f"No benchmark rows found at {input_path}")

    if args.limit:
        rows = rows[: args.limit]

    output_path = ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    review_rows: list[dict[str, Any]] = []

    with output_path.open("w", encoding="utf-8") as handle:
        for index, row in enumerate(rows, start=1):
            question_id = row.get("id")
            original_question = str(row["question"])

            paraphrases = generate_paraphrases(original_question, args.count)

            record = {
                "question_id": question_id,
                "original_question": original_question,
                "paraphrases": paraphrases,
                "reviewed": False,
                "generation_method": "ollama_paraphrase",
            }

            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

            for paraphrase in paraphrases:
                review_rows.append(
                    {
                        "question_id": question_id,
                        "original_question": original_question,
                        "paraphrase": paraphrase,
                        "preserves_intended_answer": "",
                        "reviewer_notes": "",
                    }
                )

            print(
                f"[{index}/{len(rows)}] {question_id}: "
                f"{len(paraphrases)} paraphrases generated"
            )

    review_csv_path = ROOT / args.review_csv

    with review_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "question_id",
                "original_question",
                "paraphrase",
                "preserves_intended_answer",
                "reviewer_notes",
            ],
        )
        writer.writeheader()
        writer.writerows(review_rows)

    print(f"\nWrote paraphrases to: {output_path}")
    print(f"Wrote manual-review sheet to: {review_csv_path}")
    print(
        "\nDo not use a paraphrase in leakage_check.py or any evaluation "
        "run until its 'preserves_intended_answer' column has been filled "
        "in by a reviewer."
    )


if __name__ == "__main__":
    main()

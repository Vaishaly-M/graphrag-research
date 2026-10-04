from __future__ import annotations

import argparse
from typing import Any

from src.llm import GeminiClient
from src.systems.base import (
    BaseSystem,
    add_run_arguments,
)
from src.systems.prompts import ANSWER_MAX_OUTPUT_TOKENS, ANSWER_TEMPERATURE


class System(BaseSystem):
    name = "plain_llm"

    def __init__(self) -> None:
        self.llm = GeminiClient()

    def answer(
        self,
        question: str,
    ) -> dict[str, Any]:
        prompt = (
            "Answer the following software repository question "
            "concisely.\n\n"
            "You do not have access to repository retrieval, a "
            "knowledge graph, source-code search, or external "
            "repository evidence.\n\n"
            "Use only the information contained in the question "
            "and your general knowledge. Do not invent repository-"
            "specific files, classes, functions, developers, "
            "commits, issues, dependencies, paths, or values.\n\n"
            "When the question requires repository-specific "
            "information that is not provided, clearly state that "
            "the available information is insufficient.\n\n"
            f"QUESTION:\n{question}"
        )

        answer = self.llm.generate(
            prompt,
            temperature=ANSWER_TEMPERATURE,
            max_output_tokens=ANSWER_MAX_OUTPUT_TOKENS,
        )

        return {
            "answer": answer,
            "selected_retrieval_route": "none",
            "retrieved_evidence": [],
            "generated_cypher": None,
            "predicted_relations": [],
            "predicted_path": [],
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Plain LLM repository "
            "question-answering baseline."
        )
    )

    add_run_arguments(
        parser
    )

    args = parser.parse_args()

    system = System()

    system.run(
        benchmark=args.benchmark_file,
        output_dir=args.output_dir,
        limit=args.limit,
        reset=args.reset,
        repeats=args.repeats,
    )


if __name__ == "__main__":
    main()
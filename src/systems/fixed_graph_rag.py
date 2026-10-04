"""
Fixed Graph RAG: graph retrieval using only the registered Cypher template
registry (src/systems/query_registry.py) -- no LLM-generated Cypher
fallback.

If no template matches the question, the system abstains rather than
asking an LLM to write Cypher. This isolates how well graph retrieval
performs with routing variability and free-form query generation removed
entirely: the ceiling of "graph alone, hand-authored templates only," for
comparison against langchain_graphrag / llamaindex_graphrag (which always
fall back to LLM-generated Cypher when no template exists) and against
adaptive_hybrid_graphrag (which routes and falls back).
"""

from __future__ import annotations

import argparse
import json

from src.common import safe_read_cypher
from src.graph import Graph
from src.llm import GeminiClient
from src.systems.base import BaseSystem, add_run_arguments
from src.systems.prompts import ANSWER, ANSWER_MAX_OUTPUT_TOKENS, ANSWER_TEMPERATURE
from src.systems.query_registry import match_registered_query
from src.systems.retrieval_core import direct_answers, run_graph_query


class System(BaseSystem):
    name = "fixed_graph_rag"

    def __init__(self) -> None:
        self.llm = GeminiClient()
        self.graph = Graph()

    def answer(self, question: str) -> dict:
        match = match_registered_query(question)

        if match is None:
            return {
                "answer": "Insufficient repository evidence.",
                "selected_retrieval_route": "graph",
                "matched_template": "",
                "template_coverage_hit": False,
                "retrieved_evidence": [],
                "generated_cypher": None,
            }

        cypher = safe_read_cypher(match.cypher)
        rows, error = run_graph_query(self.graph, cypher, match.params)

        if error or not rows:
            return {
                "answer": "Insufficient repository evidence.",
                "selected_retrieval_route": "graph",
                "matched_template": match.template_name,
                "template_coverage_hit": True,
                "retrieved_evidence": [],
                "generated_cypher": cypher,
                "generated_cypher_params": match.params,
                "retrieval_errors": [error] if error else ["empty_result"],
            }

        direct = direct_answers(rows)

        if direct:
            answer = direct[0] if len(direct) == 1 else "\n".join(direct)
            mode = "deterministic_graph"
        else:
            # No template in the current registry produces rows without an
            # "answer" alias, so this branch is a defensive fallback for
            # future template additions rather than something exercised
            # today.
            evidence = {"cypher": cypher, "rows": rows}
            answer = self.llm.generate(
                ANSWER.format(
                    question=question,
                    evidence=json.dumps(evidence, ensure_ascii=False, default=str),
                ),
                temperature=ANSWER_TEMPERATURE,
                max_output_tokens=ANSWER_MAX_OUTPUT_TOKENS,
            ).strip()
            mode = "grounded_llm"

        return {
            "answer": answer,
            "answer_generation_mode": mode,
            "selected_retrieval_route": "graph",
            "matched_template": match.template_name,
            "template_coverage_hit": True,
            "retrieved_evidence": rows,
            "generated_cypher": cypher,
            "generated_cypher_params": match.params,
            "predicted_relations": list(match.expected_relations),
            "predicted_path": list(match.expected_path),
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run Fixed Graph RAG (template-registry-only, no LLM-Cypher "
            "fallback)."
        )
    )
    add_run_arguments(parser)
    args = parser.parse_args()

    System().run(
        benchmark=args.benchmark_file,
        output_dir=args.output_dir,
        limit=args.limit,
        reset=args.reset,
        repeats=args.repeats,
    )


if __name__ == "__main__":
    main()

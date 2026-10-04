"""
Oracle Hybrid RAG: reads the benchmark's own independently-generated
`expected_retrieval_route` label (graph/vector/hybrid) to pick the
retrieval strategy, instead of inferring it from the question the way
Adaptive Hybrid GraphRAG or the fixed baselines do.

This is not a practical system -- a real user's question has no gold
route label. It exists to estimate the ceiling: how much of Adaptive
Hybrid's remaining error is a genuinely hard retrieval/answering problem
versus a routing mistake it could in principle have avoided (Guide
Section 7.7).

Route lookup is by exact question-text match against the benchmark file
passed via --benchmark-file (the same file BaseSystem.run() loads). A
question that cannot be matched (e.g. a paraphrase not present in that
file) falls back to "hybrid" -- the safest single default, since hybrid
always covers whatever graph or vector alone would have covered.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.common import safe_read_cypher
from src.graph import Graph
from src.llm import GeminiClient
from src.systems.base import BaseSystem, DEFAULT_PILOT_BENCHMARK, add_run_arguments
from src.systems.prompts import ANSWER, ANSWER_MAX_OUTPUT_TOKENS, ANSWER_TEMPERATURE
from src.systems.query_registry import match_registered_query
from src.systems.retrieval_core import (
    direct_answers,
    fuse_evidence,
    generate_llm_cypher,
    graph_evidence,
    run_graph_query,
    run_vector_query,
    vector_evidence,
)
from src.vector_store import VectorStore

VALID_ROUTES = {"graph", "vector", "hybrid"}


class System(BaseSystem):
    name = "oracle_hybrid_rag"

    def __init__(self, benchmark_file: str | Path = DEFAULT_PILOT_BENCHMARK) -> None:
        self.llm = GeminiClient()
        self.graph = Graph()
        self.vector_store = VectorStore()
        self.route_by_question = self._load_route_lookup(benchmark_file)

    @staticmethod
    def _load_route_lookup(benchmark_file: str | Path) -> dict[str, str]:
        path = BaseSystem._resolve_path(benchmark_file)

        if not path.exists():
            return {}

        lookup: dict[str, str] = {}

        for row in BaseSystem._load_benchmark(path):
            question = str(row.get("question", "")).strip()
            route = str(row.get("expected_retrieval_route", "")).strip().lower()

            if question and route in VALID_ROUTES:
                lookup[question] = route

        return lookup

    def graph_side(self, question: str) -> tuple[list[dict], str, dict, str]:
        match = match_registered_query(question)

        try:
            cypher = (
                safe_read_cypher(match.cypher)
                if match
                else generate_llm_cypher(self.llm, question)
            )
        except Exception as exc:
            return [], "", {}, f"{type(exc).__name__}: {exc}"

        params = match.params if match else {}
        rows, error = run_graph_query(self.graph, cypher, params)
        return rows, cypher, params, error

    def answer(self, question: str) -> dict:
        gold_route = self.route_by_question.get(question.strip(), "hybrid")

        # An oracle should represent the best achievable routing decision,
        # not just the category-level gold label. When a registered
        # template exists for this exact question, its route reflects
        # question-specific knowledge the category-level label doesn't
        # have -- e.g. fragment_to_file always uses "hybrid" because a
        # content match benefits from both graph and vector evidence, even
        # though code_retrieval/documentation_lookup's category-level gold
        # route is "vector" (see generate_benchmark.py's
        # expected_route_for_category). Only ever widen toward hybrid,
        # never narrow away from the gold route, since hybrid retrieval is
        # a strict superset of graph-only or vector-only.
        match = match_registered_query(question)
        if match is not None and match.route == "hybrid" and gold_route != "hybrid":
            route = "hybrid"
        else:
            route = gold_route

        graph_rows: list = []
        cypher = ""
        cypher_params: dict = {}
        graph_error = ""
        vector_rows: list = []
        vector_error = ""

        if route in {"graph", "hybrid"}:
            graph_rows, cypher, cypher_params, graph_error = self.graph_side(question)

        if route in {"vector", "hybrid"}:
            vector_rows, vector_error = run_vector_query(self.vector_store, question)

        fused = fuse_evidence(
            question, graph_evidence(graph_rows) + vector_evidence(vector_rows)
        )

        direct = direct_answers(graph_rows)

        if direct:
            answer = direct[0] if len(direct) == 1 else "\n".join(direct)
            mode = "deterministic_graph"
        elif fused:
            payload = [
                {
                    "rank": i,
                    "source": e.source,
                    "evidence_id": e.evidence_id,
                    "score": round(e.score, 6),
                    "content": e.content,
                }
                for i, e in enumerate(fused, 1)
            ]
            answer = self.llm.generate(
                ANSWER.format(
                    question=question,
                    evidence=json.dumps(payload, ensure_ascii=False, default=str),
                ),
                temperature=ANSWER_TEMPERATURE,
                max_output_tokens=ANSWER_MAX_OUTPUT_TOKENS,
            ).strip()
            mode = "grounded_llm"
        else:
            answer = "Insufficient repository evidence."
            mode = "no_evidence"

        return {
            "answer": answer,
            "answer_generation_mode": mode,
            "selected_retrieval_route": route,
            "oracle_route_source": (
                "benchmark_expected_retrieval_route"
                if question.strip() in self.route_by_question
                else "default_hybrid_fallback"
            ),
            "retrieved_evidence": [e.evidence_id for e in fused],
            "generated_cypher": cypher or None,
            "generated_cypher_params": cypher_params,
            "graph_retrieval_count": len(graph_rows),
            "vector_retrieval_count": len(vector_rows),
            "reranked_evidence_count": len(fused),
            "retrieval_errors": [
                x
                for x in (
                    graph_error,
                    f"vector_retrieval: {vector_error}" if vector_error else "",
                )
                if x
            ],
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Oracle Hybrid RAG (routes using gold expected_retrieval_route)."
    )
    add_run_arguments(parser)
    args = parser.parse_args()

    system = System(benchmark_file=args.benchmark_file)
    system.run(
        benchmark=args.benchmark_file,
        output_dir=args.output_dir,
        limit=args.limit,
        reset=args.reset,
        repeats=args.repeats,
    )


if __name__ == "__main__":
    main()

"""
Fixed Hybrid RAG: always retrieves from both the knowledge graph and the
vector index (no adaptive routing decision), fuses the evidence via
src/systems/retrieval_core.fuse_evidence(), and answers.

Graph retrieval uses the same registered-template-first,
LLM-Cypher-fallback strategy as adaptive_hybrid_graphrag, so the only
intentional difference between this system and Adaptive Hybrid GraphRAG
is the routing decision itself: Fixed Hybrid always runs both sources,
Adaptive Hybrid decides which to run per question. This isolates whether
hybrid retrieval helps at all, independent of whether *choosing* when to
use it helps further (Guide Section 7.5).
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


class System(BaseSystem):
    name = "fixed_hybrid_rag"

    def __init__(self) -> None:
        self.llm = GeminiClient()
        self.graph = Graph()
        self.vector_store = VectorStore()

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
        graph_rows, cypher, cypher_params, graph_error = self.graph_side(question)
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
            "selected_retrieval_route": "hybrid",
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
        description="Run Fixed Hybrid RAG (always graph + vector, no routing)."
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

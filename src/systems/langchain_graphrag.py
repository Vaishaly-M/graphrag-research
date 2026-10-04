import argparse
import json

from src.common import dedupe_context
from src.graph import Graph
from src.llm import GeminiClient
from src.systems.base import BaseSystem, add_run_arguments
from src.systems.prompts import ANSWER, ANSWER_MAX_OUTPUT_TOKENS, ANSWER_TEMPERATURE
from src.systems.retrieval_core import generate_llm_cypher


class System(BaseSystem):
    """Controlled NL-to-Cypher followed by evidence-to-answer pipeline."""

    name = "langchain_graphrag"

    def __init__(self) -> None:
        self.llm = GeminiClient()
        self.graph = Graph()

    def answer(self, question: str) -> dict:
        cypher = generate_llm_cypher(self.llm, question)
        graph_rows = dedupe_context(self.graph.query(cypher))

        evidence = {
            "cypher": cypher,
            "rows": graph_rows,
        }

        answer = self.llm.generate(
            ANSWER.format(
                question=question,
                evidence=json.dumps(
                    evidence,
                    ensure_ascii=False,
                    default=str,
                ),
            ),
            temperature=ANSWER_TEMPERATURE,
            max_output_tokens=ANSWER_MAX_OUTPUT_TOKENS,
        )

        return {
            "answer": answer,
            "selected_retrieval_route": "graph",
            "retrieved_evidence": graph_rows,
            "generated_cypher": cypher,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the LangChain GraphRAG repository QA system."
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

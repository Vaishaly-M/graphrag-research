"""
Adaptive Hybrid GraphRAG.

Walks the fallback ladder from Guide Section 8.3:
  1. registered Cypher template (query_registry.py), if the router matched one
  2. read-only LLM-generated Cypher, tried when there was no template match
     or the template's own result failed evidence validation
  3. vector retrieval, run whenever the route calls for it or the graph
     side above did not produce validated evidence
  4. fuse whatever validated graph + vector evidence exists and answer;
     abstain only if nothing validated at all

This directly targets the two pilot failures found in the original
single-shot design: a registered-template match that returned zero rows
had no second attempt (developer_activity-021), and a question with no
router keyword signal defaulted to vector-only retrieval for a
structural, graph-shaped question (structure-032, compounded by an
EXTENSION_RE bug in query_registry.py that is fixed separately in this
same pass).

WP8 ablations (Guide Section 14): --no-vector/--no-graph/--no-routing/
--no-templates/--no-fallback/--no-validation/--fixed-hops/--fusion-weights
all reuse this exact codebase via AblationConfig, rather than forking a
separate copy per variant, so every ablation differs from the full system
by exactly one mechanism.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

from src.common import safe_read_cypher
from src.systems.base import BaseSystem, add_run_arguments
from src.systems.prompts import (
    ADAPTIVE_FINAL_ANSWER,
    ANSWER_MAX_OUTPUT_TOKENS,
    ANSWER_TEMPERATURE,
)
from src.systems.query_registry import QueryMatch, match_registered_query
from src.systems.router import RoutingDecision, classify
from src.systems.retrieval_core import (
    direct_answers,
    fuse_evidence,
    generate_llm_cypher,
    graph_evidence,
    repo_from_question,
    run_graph_query,
    run_vector_query,
    validate_evidence,
    vector_evidence,
)
from src.graph import Graph
from src.llm import GeminiClient
from src.vector_store import VectorStore


@dataclass(frozen=True)
class AblationConfig:
    no_vector: bool = False
    no_graph: bool = False
    no_routing: bool = False
    no_templates: bool = False
    no_fallback: bool = False
    no_validation: bool = False
    fixed_hops: int | None = None
    fusion_weights: tuple[float, float, float] | None = None

    def __post_init__(self) -> None:
        if self.no_vector and self.no_graph:
            raise ValueError(
                "Ablation config disables both graph and vector retrieval; "
                "the system would never have any evidence source."
            )


class System(BaseSystem):
    name = "adaptive_hybrid_graphrag"

    def __init__(self, ablation: AblationConfig | None = None) -> None:
        self.graph = Graph()
        self.vector_store = VectorStore()
        self.llm = GeminiClient()
        self.ablation = ablation or AblationConfig()

    def llm_cypher(self, question: str) -> str:
        return generate_llm_cypher(
            self.llm, question, hop_hint=self.ablation.fixed_hops
        )

    def _graph_rung(
        self, question: str, *, cypher: str, params: dict, rung: str, template_name: str
    ) -> dict:
        """Execute one graph-retrieval rung and validate its result."""
        rows, error = run_graph_query(self.graph, cypher, params)

        if error:
            return {
                "rung": rung, "template_name": template_name, "cypher": cypher,
                "params": params, "rows": rows, "error": error, "valid": False,
                "problems": ["query_execution_error"],
            }

        if self.ablation.no_validation:
            valid, problems = bool(rows), ([] if rows else ["empty_result"])
        else:
            valid, problems = validate_evidence(
                question, rows, params=params,
                expected_repo=repo_from_question(question), cypher=cypher,
            )

        return {
            "rung": rung, "template_name": template_name, "cypher": cypher,
            "params": params, "rows": rows, "error": "", "valid": valid,
            "problems": problems,
        }

    def collect_graph_evidence(
        self, question: str, match: QueryMatch | None
    ) -> list[dict]:
        """
        Rungs 1 and 2 of the fallback ladder: registered template first,
        then LLM-generated Cypher if there was no template or the
        template's result did not validate. Stops after the first attempt
        when the --no-fallback ablation is set, regardless of validity.
        """
        attempts: list[dict] = []

        if match is not None:
            try:
                cypher = safe_read_cypher(match.cypher)
            except Exception as exc:
                attempts.append({
                    "rung": "registered_template", "template_name": match.template_name,
                    "cypher": match.cypher, "params": match.params, "rows": [],
                    "error": f"{type(exc).__name__}: {exc}", "valid": False,
                    "problems": ["cypher_validation_failed"],
                })
            else:
                attempts.append(
                    self._graph_rung(
                        question, cypher=cypher, params=match.params,
                        rung="registered_template", template_name=match.template_name,
                    )
                )

            if attempts[-1]["valid"] or self.ablation.no_fallback:
                return attempts

        try:
            cypher = self.llm_cypher(question)
        except Exception as exc:
            attempts.append({
                "rung": "llm_cypher", "template_name": "", "cypher": "", "params": {},
                "rows": [], "error": f"{type(exc).__name__}: {exc}", "valid": False,
                "problems": ["cypher_generation_failed"],
            })
            return attempts

        attempts.append(
            self._graph_rung(
                question, cypher=cypher, params={}, rung="llm_cypher", template_name=""
            )
        )
        return attempts

    def grounded(self, question: str, evidence) -> str:
        if not evidence:
            return "Insufficient repository evidence."

        payload = [
            {
                "rank": i, "source": e.source, "evidence_id": e.evidence_id,
                "score": round(e.score, 6), "content": e.content,
            }
            for i, e in enumerate(evidence, 1)
        ]
        # Use the shared answer token budget here, not MAX_CYPHER_TOKENS --
        # this is the final-answer call, not Cypher generation, and every
        # other system's answer call gets ANSWER_MAX_OUTPUT_TOKENS. Capping
        # this one at the (shorter) Cypher budget was an unintended
        # disadvantage specific to this system.
        return self.llm.generate(
            ADAPTIVE_FINAL_ANSWER.format(
                question=question,
                evidence=json.dumps(payload, ensure_ascii=False, default=str),
            ),
            temperature=ANSWER_TEMPERATURE,
            max_output_tokens=ANSWER_MAX_OUTPUT_TOKENS,
        ).strip()

    def _resolve_route(self, decision: RoutingDecision) -> str:
        """Apply --no-routing/--no-graph/--no-vector to the router's decision."""
        route = "hybrid" if self.ablation.no_routing else decision.retrieval_plan

        if self.ablation.no_graph:
            route = "vector"
        elif self.ablation.no_vector:
            route = "graph"

        return route

    def answer(self, question: str) -> dict:
        match = None if self.ablation.no_templates else match_registered_query(question)
        decision: RoutingDecision = classify(question)
        route = self._resolve_route(decision)

        graph_attempts: list[dict] = []
        vector_rows: list = []
        vector_error = ""
        fallback_used = False

        if route in {"graph", "hybrid"}:
            graph_attempts = self.collect_graph_evidence(question, match)
            if len(graph_attempts) > 1:
                fallback_used = True  # the template rung did not validate

        best_graph = next((a for a in graph_attempts if a["valid"]), None)
        graph_rows = best_graph["rows"] if best_graph else []

        # Rung 3: vector retrieval, run when the route calls for it, or
        # (unless --no-fallback) when graph was supposed to answer this
        # alone but produced nothing valid -- a graph-only route
        # escalating to hybrid.
        need_vector = route in {"vector", "hybrid"} or (
            route == "graph" and best_graph is None and not self.ablation.no_fallback
        )

        if need_vector:
            if route == "graph" and best_graph is None:
                fallback_used = True  # graph-only route needed a vector rescue
            vector_rows, vector_error = run_vector_query(self.vector_store, question)

        fused = fuse_evidence(
            question,
            graph_evidence(graph_rows) + vector_evidence(vector_rows),
            weights=self.ablation.fusion_weights,
        )
        # Guide Section 8.2 "stricter evidence validation" for the low
        # -confidence band: never trust a single Cypher row deterministically
        # when the router's initial signal was weak. Always synthesize from
        # the full fused evidence pool instead, so vector corroboration (or
        # its absence) can influence the answer. Suppressed under
        # --no-routing, since there is no router confidence to be strict
        # about in that ablation.
        strict = decision.strict_validation and not self.ablation.no_routing
        direct = [] if strict else direct_answers(graph_rows)

        if direct:
            answer_text = direct[0] if len(direct) == 1 else "\n".join(direct)
            mode = "deterministic_graph"
        elif fused:
            answer_text = self.grounded(question, fused)
            mode = "grounded_llm"
        else:
            answer_text = "Insufficient repository evidence."
            mode = "abstained"
            fallback_used = True

        evidence_sources = [
            source
            for source, rows in (("graph", graph_rows), ("vector", vector_rows))
            if rows
        ]

        last_attempt = graph_attempts[-1] if graph_attempts else None

        return {
            "answer": answer_text,
            "answer_generation_mode": mode,
            "selected_retrieval_route": route,
            "actual_evidence_sources": evidence_sources,
            "router_intent": decision.intent,
            "router_confidence": decision.confidence,
            "router_preferred_route": decision.preferred_route,
            "router_strict_validation": decision.strict_validation,
            "router_hops": decision.hops,
            "matched_template": match.template_name if match else "",
            "template_coverage_hit": match is not None,
            "fallback_used": fallback_used,
            "fallback_rungs_tried": [a["rung"] for a in graph_attempts]
            + (["vector"] if need_vector else []),
            "graph_attempts": [
                {
                    "rung": a["rung"],
                    "template_name": a["template_name"],
                    "valid": a["valid"],
                    "problems": a["problems"],
                    "row_count": len(a["rows"]),
                }
                for a in graph_attempts
            ],
            "retrieved_evidence": [e.evidence_id for e in fused],
            "predicted_relations": (
                list(match.expected_relations) if match and best_graph else []
            ),
            "predicted_path": (
                list(match.expected_path) if match and best_graph else []
            ),
            "generated_cypher": best_graph["cypher"] if best_graph else (
                last_attempt["cypher"] if last_attempt else None
            ),
            "generated_cypher_params": best_graph["params"] if best_graph else {},
            "graph_query_results": graph_rows,
            "vector_retrieval_count": len(vector_rows),
            "graph_retrieval_count": len(graph_rows),
            "reranked_evidence_count": len(fused),
            "retrieval_errors": [
                x
                for x in (
                    last_attempt["error"] if last_attempt and not best_graph else "",
                    f"vector_retrieval: {vector_error}" if vector_error else "",
                )
                if x
            ],
            "ablation_config": {
                "no_vector": self.ablation.no_vector,
                "no_graph": self.ablation.no_graph,
                "no_routing": self.ablation.no_routing,
                "no_templates": self.ablation.no_templates,
                "no_fallback": self.ablation.no_fallback,
                "no_validation": self.ablation.no_validation,
                "fixed_hops": self.ablation.fixed_hops,
                "fusion_weights": self.ablation.fusion_weights,
            },
        }


def _parse_fusion_weights(raw: str | None) -> tuple[float, float, float] | None:
    if raw is None:
        return None

    parts = [part.strip() for part in raw.split(",")]

    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            "--fusion-weights must be three comma-separated numbers: "
            "retrieval,lexical,graph_bonus"
        )

    try:
        return (float(parts[0]), float(parts[1]), float(parts[2]))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--fusion-weights values must be numbers: {raw}"
        ) from exc


def add_ablation_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--no-vector", action="store_true")
    parser.add_argument("--no-graph", action="store_true")
    parser.add_argument("--no-routing", action="store_true")
    parser.add_argument("--no-templates", action="store_true")
    parser.add_argument("--no-fallback", action="store_true")
    parser.add_argument("--no-validation", action="store_true")
    parser.add_argument("--fixed-hops", type=int, default=None)
    parser.add_argument("--fusion-weights", type=str, default=None)


def ablation_config_from_args(args: argparse.Namespace) -> AblationConfig:
    return AblationConfig(
        no_vector=args.no_vector,
        no_graph=args.no_graph,
        no_routing=args.no_routing,
        no_templates=args.no_templates,
        no_fallback=args.no_fallback,
        no_validation=args.no_validation,
        fixed_hops=args.fixed_hops,
        fusion_weights=_parse_fusion_weights(args.fusion_weights),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run Adaptive Hybrid GraphRAG (router + fallback ladder)."
    )
    add_run_arguments(parser)
    add_ablation_arguments(parser)
    args = parser.parse_args()

    System(ablation=ablation_config_from_args(args)).run(
        benchmark=args.benchmark_file,
        output_dir=args.output_dir,
        limit=args.limit,
        reset=args.reset,
        repeats=args.repeats,
    )

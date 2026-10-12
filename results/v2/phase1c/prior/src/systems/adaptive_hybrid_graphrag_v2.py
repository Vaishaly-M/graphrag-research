"""New router and symmetric safety escalation; old adaptive system remains available."""
import json
from pathlib import Path
from src.common import ROOT, config_get
from src.systems.adaptive_hybrid_graphrag import System as OriginalSystem
from src.systems.query_registry import match_registered_query
from src.systems.retrieval_core import direct_answers, fuse_evidence, graph_evidence, vector_evidence, run_vector_query
from src.systems.router_v2 import EntityCatalog, load_frozen, retrieve_with_fallback


class System(OriginalSystem):
    name = "adaptive_hybrid_graphrag_v2"

    def __init__(self, router=None, ablation=None, enable_safety_fallback=True):
        super().__init__(ablation)
        self.minimum_vector_score = float(config_get("router_v2.minimum_vector_score", .3))
        if router is None:
            directory = ROOT / str(config_get("router_v2.artifact_directory", "results/v2/phase2"))
            config = json.loads((directory / "frozen_router.json").read_text(encoding="utf-8"))
            self.minimum_vector_score = float(config["minimum_vector_score"])
            if config["embedding_model"] != self.vector_store.model_name:
                raise ValueError("Frozen router embedding model mismatch")
            records = json.loads((directory / "entity_catalog.json").read_text(encoding="utf-8"))
            router = load_frozen(directory / "frozen_router.json", EntityCatalog(records), self.vector_store.model, self.llm)
        self.router = router
        self.enable_safety_fallback = enable_safety_fallback

    def answer(self, question):
        match = None if self.ablation.no_templates else match_registered_query(question)
        decision = self.router.classify(question)
        route = self._resolve_route(decision)
        attempts, vector_errors = [], []
        def graph_retrieve():
            attempts.extend(self.collect_graph_evidence(question, match))
            best = next((a for a in attempts if a["valid"]), None)
            return best["rows"] if best else []
        def vector_retrieve():
            rows, error = run_vector_query(self.vector_store, question)
            if error:
                vector_errors.append(error)
            return rows
        evidence = retrieve_with_fallback(route, graph_retrieve, vector_retrieve,
            minimum_vector_score=self.minimum_vector_score,
            enabled=self.enable_safety_fallback and not any((self.ablation.no_fallback, self.ablation.no_graph, self.ablation.no_vector)))
        graph_rows, vector_rows = evidence["graph"], evidence["vector"]
        fused = fuse_evidence(question, graph_evidence(graph_rows)+vector_evidence(vector_rows), weights=self.ablation.fusion_weights)
        # Graph evidence has already passed validation. Routing confidence must not
        # silently change the answer-generation policy used for forced-route outcomes.
        direct = direct_answers(graph_rows)
        if direct:
            answer, mode = "\n".join(direct), "deterministic_graph"
        elif fused:
            answer, mode = self.grounded(question, fused), "grounded_llm"
        else:
            answer, mode = "Insufficient repository evidence.", "abstained"
        best = next((a for a in attempts if a["valid"]), None)
        return dict(answer=answer, answer_generation_mode=mode,
            selected_retrieval_route=route, executed_retrieval_route=evidence["executed_route"],
            fallback_used=evidence["fallback_used"] or len(attempts)>1,
            fallback_reason=evidence["fallback_reason"], router_scores=decision.scores,
            router_features=decision.features, routing_metadata=decision.to_dict(),
            router_confidence=decision.confidence, router_preferred_route=decision.preferred_route,
            router_hops=decision.hops, graph_retrieval_count=len(graph_rows), vector_retrieval_count=len(vector_rows),
            vector_max_score=max((float(v.get("score",0)) for v in vector_rows),default=None),
            retrieved_evidence=[e.evidence_id for e in fused], graph_attempts=attempts,
            generated_cypher=best["cypher"] if best else None,
            generated_cypher_params=best["params"] if best else {},
            actual_evidence_sources=[s for s, rows in [("graph",graph_rows),("vector",vector_rows)] if rows],
            retrieval_errors=vector_errors+[a["error"] for a in attempts if a.get("error")])

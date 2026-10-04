"""
Rule-based intent classifier for repository questions (Guide Section 8.1).

No extra LLM call -- confidence is derived from match specificity, so
routing cost and latency stay comparable to the pre-router design:

  - a registered Cypher template match (query_registry.py) is the most
    specific signal available: confidence 0.95.
  - a clear multi-hop marker phrase (this benchmark's own multi-hop
    templates use "modified through commits authored by" / "authored
    commits that modified", plus generic dependency-impact phrasing) is
    fairly distinctive: confidence 0.75.
  - both graph and vector keyword families appear with no multi-hop
    marker: confidence 0.65 (genuinely ambiguous -- Guide's medium band).
  - exactly one keyword family present: confidence 0.55.
  - no signal at all: confidence 0.30 (Guide's low band: try both sources
    and validate more strictly, rather than the old design's default
    guess of "vector").

adaptive_hybrid_graphrag.py consumes RoutingDecision.confidence against
the thresholds in config/experiment.yaml -> router to decide how far down
the fallback ladder (Guide Section 8.3) to go.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.common import config_get
from src.systems.query_registry import QueryMatch, match_registered_query
from src.systems.retrieval_core import normalize

HIGH_CONFIDENCE_THRESHOLD = float(
    config_get("router.high_confidence_threshold", 0.85)
)
MEDIUM_CONFIDENCE_THRESHOLD = float(
    config_get("router.medium_confidence_threshold", 0.60)
)

TEMPLATE_CONFIDENCE = 0.95
MULTI_HOP_CONFIDENCE = 0.75
BOTH_KEYWORD_FAMILIES_CONFIDENCE = 0.65
SINGLE_KEYWORD_FAMILY_CONFIDENCE = 0.55
NO_SIGNAL_CONFIDENCE = 0.30

GRAPH_KEYWORDS = (
    "commit", "issue", "pull request", "repository contains", "assigned",
    "modified", "merged", "dependency", "developer", "contributor",
)
VECTOR_KEYWORDS = (
    "code fragment", "contains the text", "documentation", "readme",
    "implementation", "function", "class", "method", "snippet",
)
# Phrases distinctive to genuinely multi-hop questions. "authored by
# developer" alone is deliberately excluded -- it also appears in this
# benchmark's single-hop developer_commits_in_repository questions, and
# including it there mis-routed plain single-hop questions to "hybrid" in
# the original heuristic.
MULTI_HOP_MARKERS = (
    "modified through commits authored by",
    "authored commits that modified",
    "depends on",
    "dependency path",
    "impact of",
)


@dataclass(frozen=True)
class RoutingDecision:
    intent: str
    retrieval_plan: str  # "graph" | "vector" | "hybrid" -- after band policy
    preferred_route: str  # the route the signal itself pointed to, pre-band
    hops: int
    answer_type: str
    confidence: float
    matched_template: str  # "" if no registry match
    strict_validation: bool  # True below the medium-confidence band


def _hop_count_for_template(match: QueryMatch) -> int:
    if not match.expected_path:
        return 1
    # expected_path lists Node, Relationship, Node, ... triples; hop count
    # is the number of relationship steps in that path.
    return max(1, (len(match.expected_path) - 1) // 2)


def _raw_signal(
    question: str,
) -> tuple[str, str, float, str, int, str]:
    """
    Compute (intent, preferred_route, confidence, answer_type, hops,
    matched_template) from the question text alone, before the
    confidence-band policy is applied.
    """
    match = match_registered_query(question)

    if match is not None:
        answer_type = (
            "ranked_list"
            if match.template_name == "top_repository_contributors"
            else "multiple_entities"
        )
        return (
            match.template_name, match.route, TEMPLATE_CONFIDENCE, answer_type,
            _hop_count_for_template(match), match.template_name,
        )

    normalized = normalize(question)

    if any(marker in normalized for marker in MULTI_HOP_MARKERS):
        return (
            "multi_hop_relationship", "hybrid", MULTI_HOP_CONFIDENCE,
            "multiple_entities", 3, "",
        )

    graph_signals = sum(keyword in normalized for keyword in GRAPH_KEYWORDS)
    vector_signals = sum(keyword in normalized for keyword in VECTOR_KEYWORDS)

    if graph_signals and vector_signals:
        return (
            "hybrid_signal", "hybrid", BOTH_KEYWORD_FAMILIES_CONFIDENCE,
            "multiple_entities", 2, "",
        )

    if graph_signals or vector_signals:
        plan = "graph" if graph_signals > vector_signals else "vector"
        intent = "graph_signal" if plan == "graph" else "vector_signal"
        return (intent, plan, SINGLE_KEYWORD_FAMILY_CONFIDENCE, "multiple_entities", 1, "")

    return ("unsupported", "hybrid", NO_SIGNAL_CONFIDENCE, "multiple_entities", 1, "")


def classify(question: str) -> RoutingDecision:
    intent, preferred_route, confidence, answer_type, hops, matched_template = (
        _raw_signal(question)
    )

    # Guide Section 8.2 confidence-band policy: only a high-confidence
    # decision is trusted to use a single-source route as-is. Medium and
    # low confidence are both forced to hybrid (try both sources); low
    # confidence additionally sets strict_validation, which
    # adaptive_hybrid_graphrag.py uses to refuse the "trust one Cypher row
    # blindly" deterministic shortcut and always synthesize the answer
    # from the full fused evidence pool instead.
    if confidence >= HIGH_CONFIDENCE_THRESHOLD:
        retrieval_plan = preferred_route
    else:
        retrieval_plan = "hybrid"

    strict_validation = confidence < MEDIUM_CONFIDENCE_THRESHOLD

    return RoutingDecision(
        intent=intent,
        retrieval_plan=retrieval_plan,
        preferred_route=preferred_route,
        hops=hops,
        answer_type=answer_type,
        confidence=confidence,
        matched_template=matched_template,
        strict_validation=strict_validation,
    )

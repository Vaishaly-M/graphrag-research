"""
Shared retrieval and evidence-fusion building blocks used by every
hybrid-style system: Fixed Graph RAG, Fixed Hybrid RAG, Oracle Hybrid RAG,
and Adaptive Hybrid GraphRAG.

Factored out of the original adaptive_hybrid_graphrag.py so "the only
intentional difference between systems is retrieval strategy" (Guide
Section 9.2) is enforced by construction: every system that fuses graph
and vector evidence calls the exact same scoring function with the exact
same weights, instead of each maintaining its own copy that could
silently drift from the others.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from src.common import config_get, dedupe_context, safe_read_cypher
from src.graph import Graph
from src.systems.prompts import CYPHER
from src.vector_store import VectorStore

VECTOR_TOP_K = int(config_get("adaptive_hybrid.vector_top_k", 10))
MAX_GRAPH_ROWS = int(config_get("adaptive_hybrid.max_graph_rows", 100))
MAX_FINAL_EVIDENCE = int(config_get("adaptive_hybrid.max_final_evidence", 16))
MAX_CYPHER_TOKENS = int(config_get("llm.max_output_tokens_cypher", 700))

FUSION_RETRIEVAL_WEIGHT = float(
    config_get("adaptive_hybrid.fusion_weights.retrieval", 0.72)
)
FUSION_LEXICAL_WEIGHT = float(
    config_get("adaptive_hybrid.fusion_weights.lexical", 0.20)
)
FUSION_GRAPH_BONUS = float(
    config_get("adaptive_hybrid.fusion_weights.graph_bonus", 0.08)
)

REPOSITORY_RE = re.compile(r"\brepository\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", re.I)


@dataclass
class Evidence:
    evidence_id: str
    source: str  # "graph" or "vector"
    content: Any
    score: float


def normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower().replace("\\", "/"))


def unique(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()

    for value in values:
        text = str(value or "").strip()
        key = normalize(text)

        if text and key not in seen:
            seen.add(key)
            output.append(text)

    return output


def repo_from_question(question: str) -> str | None:
    match = REPOSITORY_RE.search(question)
    return match.group(1) if match else None


# --------------------------------------------------------------------------
# Retrieval execution
# --------------------------------------------------------------------------

def run_graph_query(
    graph: Graph, cypher: str, params: dict[str, Any]
) -> tuple[list[dict[str, Any]], str]:
    """
    Execute one already-validated Cypher query.

    Returns (rows, error) -- error is "" on success, so callers can record
    a partial failure without an exception aborting the whole answer()
    call, matching the original adaptive-system behavior.
    """
    try:
        rows = dedupe_context(graph.query(cypher, **params))[:MAX_GRAPH_ROWS]
        return rows, ""
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"


def generate_llm_cypher(
    llm,
    question: str,
    *,
    hop_hint: int | None = None,
    preamble: str = "",
) -> str:
    """
    Ask the LLM for read-only Cypher and validate it before returning.

    hop_hint (WP8 --fixed-hops ablation) appends an explicit relationship
    -count constraint to the prompt. It only affects this LLM-generated
    -Cypher rung -- a registered template's hop count is fixed by its own
    hand-authored Cypher and cannot be overridden per-call.
    """
    prompt = preamble + CYPHER.format(question=question)

    if hop_hint is not None:
        prompt += (
            f"\nThe query must traverse exactly {hop_hint} relationship "
            "hop(s) -- no more, no fewer."
        )

    raw = llm.generate(
        prompt,
        temperature=0.0,
        max_output_tokens=MAX_CYPHER_TOKENS,
    )

    try:
        return safe_read_cypher(raw)
    except ValueError as first_error:
        # A model can occasionally emit a write clause despite the prompt.
        # Regenerate once with the exact safety failure before giving up.
        # This preserves the graph-only retrieval design while avoiding an
        # otherwise recoverable failed benchmark row.
        repaired = llm.generate(
            prompt
            + "\nYour previous output was rejected: "
            + str(first_error)
            + " Regenerate one read-only Cypher query. Do not use CREATE, "
            "MERGE, DELETE, SET, REMOVE, DROP, LOAD CSV, FOREACH, or "
            "write procedures.",
            temperature=0.0,
            max_output_tokens=MAX_CYPHER_TOKENS,
        )
        return safe_read_cypher(repaired)


def run_vector_query(
    vector_store: VectorStore, question: str, *, k: int = VECTOR_TOP_K
) -> tuple[list[dict[str, Any]], str]:
    try:
        rows = vector_store.search(
            question, k=k, repository=repo_from_question(question)
        )
        return rows, ""
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------
# Evidence construction, lexical scoring, and fusion
# --------------------------------------------------------------------------

def graph_evidence(rows: list[dict[str, Any]]) -> list[Evidence]:
    output: list[Evidence] = []

    for index, row in enumerate(rows, 1):
        value = row.get("answer") if isinstance(row, dict) else None
        evidence_id = (
            str(value)
            if value not in (None, "", [], {})
            else json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        )
        output.append(
            Evidence(
                f"graph:{evidence_id}", "graph", row, max(0.70, 1 - 0.01 * (index - 1))
            )
        )

    return output


def vector_evidence(rows: list[dict[str, Any]]) -> list[Evidence]:
    return [
        Evidence(
            f"vector:{row.get('artifact_id', row.get('id', index))}",
            "vector",
            row,
            float(row.get("score", 1 / index)),
        )
        for index, row in enumerate(rows, 1)
    ]


def lexical_overlap(question: str, evidence: Evidence) -> float:
    question_tokens = set(re.findall(r"[a-z0-9_./#@:+\-]+", normalize(question)))
    evidence_tokens = set(
        re.findall(
            r"[a-z0-9_./#@:+\-]+",
            normalize(json.dumps(evidence.content, ensure_ascii=False, default=str)),
        )
    )
    return (
        len(question_tokens & evidence_tokens) / len(question_tokens)
        if question_tokens
        else 0.0
    )


def fuse_evidence(
    question: str,
    items: list[Evidence],
    *,
    max_final: int = MAX_FINAL_EVIDENCE,
    weights: tuple[float, float, float] | None = None,
) -> list[Evidence]:
    """
    Score and merge graph+vector evidence into one ranked list, deduplicated
    by normalized evidence id. Every system that fuses evidence must call
    this function rather than reimplementing the scoring formula, so a
    fusion-weight change applies identically everywhere it's used.

    weights overrides the configured (retrieval, lexical, graph_bonus)
    triple for this call only (WP8 --fusion-weights ablation); the module
    -level config values remain the default for every other caller.
    """
    retrieval_weight, lexical_weight, graph_bonus = (
        weights
        if weights is not None
        else (FUSION_RETRIEVAL_WEIGHT, FUSION_LEXICAL_WEIGHT, FUSION_GRAPH_BONUS)
    )

    merged: dict[str, Evidence] = {}

    for evidence in items:
        evidence.score = min(
            1,
            retrieval_weight * evidence.score
            + lexical_weight * lexical_overlap(question, evidence)
            + (graph_bonus if evidence.source == "graph" else 0),
        )
        key = (
            normalize(evidence.evidence_id)
            .removeprefix("graph:")
            .removeprefix("vector:")
        )

        if key not in merged or evidence.score > merged[key].score:
            merged[key] = evidence

    return sorted(merged.values(), key=lambda item: item.score, reverse=True)[
        :max_final
    ]


# --------------------------------------------------------------------------
# Evidence validation (Guide Section 8.4)
# --------------------------------------------------------------------------

# Long/specific tokens a correct query should be conditioned on: commit
# -like hex ids, "#123" issue references, quoted fragments, and dotted
# file paths.
_HEX_ID_RE = re.compile(r"\b[a-f0-9]{7,40}\b", re.I)
_ISSUE_REF_RE = re.compile(r"#(\d+)")
_FILE_PATH_RE = re.compile(r"\b[\w.-]+/[\w./-]+\.[A-Za-z0-9]+\b")


def _question_identifiers(question: str) -> list[str]:
    identifiers: list[str] = list(_HEX_ID_RE.findall(question))
    issue_refs = _ISSUE_REF_RE.findall(question)
    # A registered template binds the issue number as a plain integer
    # parameter (e.g. 66792), not the literal "#66792" text -- check both
    # forms so the bound-parameter form actually matches.
    identifiers += [f"#{n}" for n in issue_refs]
    identifiers += issue_refs
    identifiers += re.findall(r'"([^"]+)"', question)
    identifiers += re.findall(r"'([^']+)'", question)
    identifiers += _FILE_PATH_RE.findall(question)
    return [identifier for identifier in identifiers if identifier]


def validate_evidence(
    question: str,
    rows: list[dict[str, Any]],
    *,
    params: dict[str, Any],
    expected_repo: str | None,
    cypher: str = "",
    max_plausible_rows: int = MAX_GRAPH_ROWS,
) -> tuple[bool, list[str]]:
    """
    Sanity-check a set of graph rows before trusting them as evidence.

    Checks are run against the union of the query's bound parameters and
    the raw Cypher text, not parameters alone: a registered template binds
    identifiers as $parameters, but LLM-generated Cypher (see
    src/systems/prompts.py's CYPHER template) embeds them directly as
    literals in the query string instead, so a params-only check would
    reject every valid LLM-Cypher result.

    This is not full semantic correctness of the Cypher -- it will not
    catch a query that is syntactically fine but answers a subtly
    different question. Returns (is_valid, problems); problems is always
    populated when is_valid is False so callers can log *why* a fallback
    rung was rejected.
    """
    problems: list[str] = []

    if not rows:
        return False, ["empty_result"]

    if len(rows) > max_plausible_rows:
        problems.append("implausible_row_count")

    bound_text = normalize(
        json.dumps(list(params.values()), ensure_ascii=False, default=str)
        + " "
        + cypher
    )

    if expected_repo and normalize(expected_repo) not in bound_text:
        problems.append("repository_not_bound_in_query")

    question_identifiers = _question_identifiers(question)
    if question_identifiers and not any(
        normalize(identifier) in bound_text for identifier in question_identifiers
    ):
        problems.append("requested_identifier_not_bound_in_query")

    # dedupe_context() already removes exact duplicates before evidence
    # reaches here; a duplicate surviving to this point signals the query
    # itself is returning a cartesian product rather than a targeted match.
    serialized_rows = [
        json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        for row in rows
    ]
    if len(serialized_rows) != len(set(serialized_rows)):
        problems.append("duplicate_rows_after_dedupe")

    return not problems, problems


def direct_answers(rows: list[dict[str, Any]]) -> list[str]:
    """
    Extract deterministic answer values directly from Cypher rows shaped
    as {"answer": ...}. Returns [] if any row lacks an 'answer' key, since
    that means the query wasn't a plain lookup and needs LLM synthesis.
    """
    values: list[str] = []

    for row in rows:
        if not isinstance(row, dict) or "answer" not in row:
            return []

        value = row.get("answer")

        if isinstance(value, (list, tuple, set)):
            values.extend(str(item) for item in value if item not in (None, ""))
        elif value not in (None, ""):
            values.append(str(value))

    return unique(values)

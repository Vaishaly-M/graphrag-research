"""Fair repository-QA evaluator for five RAG/GraphRAG systems.

Run:

    python -m src.evaluation.metrics \
        --input-dir results/pilot_raw \
        --benchmark-file data/benchmark/benchmark_pilot_7.csv \
        --output-dir results/pilot_evaluation

Optional:

    python -m src.evaluation.metrics \
        --input-dir results/pilot_raw \
        --benchmark-file data/benchmark/benchmark_pilot_7.csv \
        --output-dir results/pilot_evaluation \
        --bert-score
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
import sys
import warnings
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


SYSTEMS = {
    "adaptive_hybrid_graphrag",
    "langchain_graphrag",
    "llamaindex_graphrag",
    "plain_llm",
    "vector_rag",
    "fixed_graph_rag",
    "fixed_hybrid_rag",
    "oracle_hybrid_rag",
}

OUTPUTS = {
    "per_question_metrics.csv",
    "summary_metrics.csv",
    "evaluation_errors.csv",
}

ALIASES = {
    "question_id": [
        "question_id",
        "id",
        "qid",
    ],
    "question": [
        "question",
        "query",
        "prompt",
    ],
    "answer": [
        "answer",
        "generated_answer",
        "prediction",
        "response",
        "system_answer",
    ],
    "expected_answer": [
        "expected_answer",
        "reference_answer",
        "ground_truth",
        "gold_answer",
    ],
    "expected_entities": [
        "expected_entities",
        "gold_entities",
        "reference_entities",
    ],
    "predicted_entities": [
        "predicted_entities",
        "answer_entities",
        "generated_entities",
    ],
    "required_facts": [
        "required_facts",
        "gold_facts",
        "expected_facts",
    ],
    "expected_relations": [
        "expected_relations",
        "gold_relations",
        "reference_relations",
    ],
    "predicted_relations": [
        "predicted_relations",
        "answer_relations",
        "generated_relations",
    ],
    "expected_path": [
        "expected_path",
        "gold_path",
        "reasoning_path",
    ],
    "predicted_path": [
        "predicted_path",
        "generated_path",
    ],
    "gold_evidence": [
        "gold_evidence",
        "expected_evidence",
        "reference_evidence",
    ],
    "retrieved_evidence": [
        "retrieved_evidence",
        "retrieval_results",
        "contexts",
        "context",
    ],
    "expected_retrieval_route": [
        "expected_retrieval_route",
        "gold_route",
        "expected_route",
    ],
    "selected_retrieval_route": [
        "selected_retrieval_route",
        "retrieval_route",
        "route",
    ],
    "generated_claims": [
        "generated_claims",
        "claims",
        "answer_claims",
    ],
    "category": [
        "category",
        "question_category",
        "type",
    ],
    "difficulty_level": [
        "difficulty_level",
        "difficulty",
    ],
    "latency_s": [
        "latency_s",
        "latency",
        "response_time_s",
    ],
    "token_usage": [
        "token_usage",
        "total_tokens",
        "tokens",
    ],
    "retrieved_context_tokens": [
        "retrieved_context_tokens",
        "context_tokens",
        "retrieval_tokens",
    ],
    "error": [
        "error",
        "error_message",
        "exception",
    ],
}


WORD_RE = re.compile(
    r"[a-z0-9_./#@:+\-]+",
    re.I,
)

PATH_RE = re.compile(
    r"(?<![\w.-])"
    r"(?:[\w.@+\-]+[\\/])+"
    r"[\w.@+\-]+"
    r"(?:\.[A-Za-z0-9]+)?"
)

ISSUE_RE = re.compile(
    r"(?<!\w)#\d+\b"
)

COMMIT_RE = re.compile(
    r"\b[a-f0-9]{7,40}\b",
    re.I,
)

SYMBOL_RE = re.compile(
    r"[`'\"]"
    r"([A-Za-z_][A-Za-z0-9_.$:< >\-]*)"
    r"[`'\"]"
)

EVIDENCE_PREFIX_RE = re.compile(
    r"^(repository|file|developer|commit|issue|pullrequest|"
    r"pull_request|pr)\s*:\s*",
    re.I,
)


def text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, float) and math.isnan(value):
        return ""

    return str(value).strip()


def norm(value: Any) -> str:
    value_text = text(value).lower()
    value_text = value_text.replace("\\", "/")
    value_text = re.sub(r"\s+", " ", value_text)
    value_text = re.sub(
        r"\s*([:/#=><|])\s*",
        r"\1",
        value_text,
    )

    return value_text.strip(
        " \t\r\n.,;:!?\"'`()[]{}"
    )


def parse(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, float) and math.isnan(value):
        return None

    if isinstance(
        value,
        (list, tuple, set, dict),
    ):
        return value

    value_text = str(value).strip()

    if not value_text:
        return None

    for parser_function in (
        json.loads,
        ast.literal_eval,
    ):
        try:
            return parser_function(value_text)
        except Exception:
            pass

    return value_text


def flatten(value: Any) -> list[str]:
    output: list[str] = []

    def visit(item: Any) -> None:
        item = parse(item)

        if item is None:
            return

        if isinstance(item, dict):
            if {
                "subject",
                "relation",
                "object",
            }.issubset(item):
                output.append(
                    f"{item['subject']}|"
                    f"{item['relation']}|"
                    f"{item['object']}"
                )
            else:
                for nested_value in item.values():
                    visit(nested_value)

        elif isinstance(
            item,
            (list, tuple, set),
        ):
            for nested_value in item:
                visit(nested_value)

        elif text(item):
            output.append(text(item))

    visit(value)
    return output


def uniq(items: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()

    for item in items:
        normalized = norm(item)

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(normalized)
        output.append(normalized)

    return output


def safe_div(
    numerator: float,
    denominator: float,
) -> float:
    if not denominator:
        return 0.0

    return float(numerator / denominator)


def tokens(value: Any) -> list[str]:
    return WORD_RE.findall(norm(value))


def set_prf(
    expected: Iterable[Any],
    predicted: Iterable[Any],
) -> tuple[float, float, float]:
    expected_set = set(uniq(expected))
    predicted_set = set(uniq(predicted))

    if not expected_set and not predicted_set:
        return 1.0, 1.0, 1.0

    if not expected_set:
        return 0.0, 1.0, 0.0

    if not predicted_set:
        return 0.0, 0.0, 0.0

    overlap = len(
        expected_set & predicted_set
    )

    precision = safe_div(
        overlap,
        len(predicted_set),
    )

    recall = safe_div(
        overlap,
        len(expected_set),
    )

    f1 = safe_div(
        2 * precision * recall,
        precision + recall,
    )

    return precision, recall, f1


def token_prf(
    reference: str,
    prediction: str,
) -> tuple[float, float, float]:
    reference_tokens = Counter(
        tokens(reference)
    )

    prediction_tokens = Counter(
        tokens(prediction)
    )

    overlap = sum(
        (
            reference_tokens
            & prediction_tokens
        ).values()
    )

    precision = safe_div(
        overlap,
        sum(prediction_tokens.values()),
    )

    recall = safe_div(
        overlap,
        sum(reference_tokens.values()),
    )

    f1 = safe_div(
        2 * precision * recall,
        precision + recall,
    )

    return precision, recall, f1


def contained(
    answer: str,
    expected_item: str,
) -> bool:
    normalized_answer = norm(answer)
    normalized_item = norm(expected_item)

    if not normalized_item:
        return False

    if normalized_item in normalized_answer:
        return True

    return bool(
        re.search(
            rf"(?<![a-z0-9_])"
            rf"{re.escape(normalized_item)}"
            rf"(?![a-z0-9_])",
            normalized_answer,
        )
    )


def coverage(
    answer: str,
    expected: Iterable[Any],
) -> tuple[float, float, int, int]:
    expected_items = uniq(expected)

    if not expected_items:
        return math.nan, math.nan, 0, 0

    matched = sum(
        contained(answer, item)
        for item in expected_items
    )

    coverage_value = safe_div(
        matched,
        len(expected_items),
    )

    accuracy = float(
        matched == len(expected_items)
    )

    return (
        accuracy,
        coverage_value,
        matched,
        len(expected_items),
    )


FACT_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for",
    "from", "has", "in", "is", "it", "of", "on", "or", "that",
    "the", "this", "to", "was", "were", "which", "with",
}


def content_tokens(value: Any) -> set[str]:
    """Return meaningful normalized tokens for fact comparison."""
    return {
        token
        for token in tokens(value)
        if token not in FACT_STOPWORDS
    }


def fact_matches_answer(
    fact: str,
    answer: str,
    recall_threshold: float = 0.60,
    f1_threshold: float = 0.55,
) -> bool:
    """Return True when the answer expresses the required fact.

    Repository answers are often deliberately concise. For example, the
    benchmark fact may be "The requested file is src/app.py" while the system
    correctly returns only "src/app.py". Matching is therefore bidirectional
    and also supports meaningful-token overlap without accepting unrelated text.
    """
    normalized_fact = norm(fact)
    normalized_answer = norm(answer)

    if not normalized_fact or not normalized_answer:
        return False

    # Full fact in answer, or concise answer in a longer benchmark statement.
    if contained(answer, fact) or contained(fact, answer):
        return True

    fact_tokens = content_tokens(fact)
    answer_tokens = content_tokens(answer)

    if not fact_tokens or not answer_tokens:
        return False

    overlap = fact_tokens & answer_tokens

    # A concise identifier-only answer is valid when every meaningful answer
    # token is contained in the validated fact. Require at least one
    # repository-specific token to avoid matching generic prose.
    identifier_like = any(
        any(marker in token for marker in ("/", "#", ":", ".", "@"))
        or re.fullmatch(r"[a-f0-9]{7,40}", token, flags=re.I)
        or token.isdigit()
        for token in answer_tokens
    )
    if identifier_like and answer_tokens.issubset(fact_tokens):
        return True

    if fact_tokens.issubset(answer_tokens):
        return True

    fact_recall = safe_div(len(overlap), len(fact_tokens))
    answer_precision = safe_div(len(overlap), len(answer_tokens))
    semantic_f1 = safe_div(
        2 * fact_recall * answer_precision,
        fact_recall + answer_precision,
    )

    if fact_recall >= recall_threshold and semantic_f1 >= f1_threshold:
        return True

    _, token_recall, token_f1 = token_prf(fact, answer)
    return token_recall >= recall_threshold and token_f1 >= f1_threshold

def fact_coverage(
    answer: str,
    expected_facts: Iterable[Any],
) -> tuple[float, int, int]:
    facts = uniq(expected_facts)

    if not facts:
        return math.nan, 0, 0

    matched = sum(
        fact_matches_answer(fact, answer)
        for fact in facts
    )

    return (
        safe_div(matched, len(facts)),
        matched,
        len(facts),
    )


def extract_entities(answer: str) -> list[str]:
    found: list[str] = []

    found.extend(
        PATH_RE.findall(answer)
    )

    found.extend(
        ISSUE_RE.findall(answer)
    )

    found.extend(
        COMMIT_RE.findall(answer)
    )

    found.extend(
        item.replace(" ", "")
        for item in SYMBOL_RE.findall(answer)
    )

    return uniq(
        item.rstrip(".,;:!?)]}")
        for item in found
    )


def expected_entities(
    row: pd.Series,
) -> list[str]:
    explicit = flatten(
        row.get("expected_entities")
    )

    if explicit:
        return explicit

    expected_answer = text(
        row.get("expected_answer")
    )

    if expected_answer:
        return flatten(expected_answer)

    return []


def relations(value: Any) -> list[str]:
    parsed = parse(value)

    if parsed is None:
        return []

    if isinstance(
        parsed,
        (list, tuple, set),
    ):
        values = parsed
    else:
        values = [parsed]

    output: list[str] = []

    for item in values:
        item = parse(item)

        if isinstance(item, dict):
            subject = item.get(
                "subject",
                item.get("source", ""),
            )

            relation = item.get(
                "relation",
                item.get(
                    "predicate",
                    item.get("type", ""),
                ),
            )

            obj = item.get(
                "object",
                item.get("target", ""),
            )

            output.append(
                f"{subject}|{relation}|{obj}"
            )

        elif (
            isinstance(item, (list, tuple))
            and len(item) >= 3
        ):
            output.append(
                f"{item[0]}|{item[1]}|{item[2]}"
            )

        elif text(item):
            output.append(text(item))

    return output


def claims(
    answer: str,
    explicit_claims: Any,
) -> list[str]:
    explicit = flatten(explicit_claims)

    if explicit:
        return explicit

    return [
        sentence.strip()
        for sentence in re.split(
            r"(?<=[.!?])\s+|\n+",
            answer,
        )
        if sentence.strip()
    ]


def claim_supported(
    claim: str,
    support_items: list[str],
) -> bool:
    normalized_claim = norm(claim)

    if not normalized_claim:
        return False

    for support in support_items:
        normalized_support = norm(support)

        if not normalized_support:
            continue

        if (
            normalized_support in normalized_claim
            or normalized_claim in normalized_support
        ):
            return True

        _, recall, f1 = token_prf(
            normalized_support,
            normalized_claim,
        )

        if recall >= 0.60 and f1 >= 0.55:
            return True

    return False


def grounding(
    answer: str,
    explicit_claims: Any,
    support: list[str],
    predicted_entities: list[str],
) -> tuple[float, float, int, int]:
    generated_claims = claims(
        answer,
        explicit_claims,
    )

    if not generated_claims:
        return math.nan, math.nan, 0, 0

    supported_count = sum(
        claim_supported(claim, support)
        for claim in generated_claims
    )

    normalized_support = norm(
        " ".join(support)
    )

    unsupported_entities = sum(
        1
        for entity in predicted_entities
        if norm(entity) not in normalized_support
    )

    unsupported_claims = max(
        len(generated_claims) - supported_count,
        unsupported_entities,
    )

    unsupported_claims = min(
        len(generated_claims),
        unsupported_claims,
    )

    supported_claim_rate = safe_div(
        supported_count,
        len(generated_claims),
    )

    hallucination_rate = safe_div(
        unsupported_claims,
        len(generated_claims),
    )

    return (
        supported_claim_rate,
        hallucination_rate,
        supported_count,
        len(generated_claims),
    )


def canonical_evidence(
    value: Any,
) -> str:
    normalized = norm(value)

    normalized = EVIDENCE_PREFIX_RE.sub(
        "",
        normalized,
    )

    normalized = normalized.replace(
        "pull_request:",
        "",
    )

    return normalized.strip()


def evidence_match(
    gold: str,
    retrieved: str,
) -> bool:
    gold_value = canonical_evidence(gold)
    retrieved_value = canonical_evidence(
        retrieved
    )

    if not gold_value or not retrieved_value:
        return False

    if (
        gold_value == retrieved_value
        or gold_value in retrieved_value
        or retrieved_value in gold_value
    ):
        return True

    gold_basename = gold_value.rsplit("/", 1)[-1]
    retrieved_basename = (
        retrieved_value.rsplit("/", 1)[-1]
    )

    if (
        "/" in gold_value
        and "/" in retrieved_value
        and gold_basename == retrieved_basename
    ):
        return True

    _, recall, f1 = token_prf(
        gold_value,
        retrieved_value,
    )

    return recall >= 0.75 and f1 >= 0.70


def retrieval_metrics(
    gold: list[str],
    retrieved: list[str],
    k: int,
) -> tuple[float, float, float]:
    gold_items = uniq(
        canonical_evidence(item)
        for item in gold
    )

    retrieved_items = uniq(
        canonical_evidence(item)
        for item in retrieved
    )[:k]

    if not gold_items:
        return math.nan, math.nan, math.nan

    if not retrieved_items:
        return 0.0, 0.0, 0.0

    retrieved_match_flags = [
        any(
            evidence_match(gold_item, retrieved_item)
            for gold_item in gold_items
        )
        for retrieved_item in retrieved_items
    ]

    precision = safe_div(
        sum(retrieved_match_flags),
        len(retrieved_items),
    )

    matched_gold = sum(
        any(
            evidence_match(gold_item, retrieved_item)
            for retrieved_item in retrieved_items
        )
        for gold_item in gold_items
    )

    recall = safe_div(
        matched_gold,
        len(gold_items),
    )

    first_relevant_rank = next(
        (
            rank
            for rank, matched in enumerate(
                retrieved_match_flags,
                start=1,
            )
            if matched
        ),
        None,
    )

    mrr = (
        1.0 / first_relevant_rank
        if first_relevant_rank
        else 0.0
    )

    return precision, recall, mrr


def rouge_l(
    reference: str,
    prediction: str,
) -> float:
    if not reference or not prediction:
        return 0.0

    try:
        from rouge_score import rouge_scorer
    except ImportError:
        warnings.warn(
            "Install ROUGE-L support with: "
            "pip install rouge-score"
        )
        return math.nan

    scorer = rouge_scorer.RougeScorer(
        ["rougeL"],
        use_stemmer=True,
    )

    return float(
        scorer.score(
            reference,
            prediction,
        )["rougeL"].fmeasure
    )


def canonical(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    lowered = {
        str(column).lower(): column
        for column in dataframe.columns
    }

    rename: dict[str, str] = {}

    for target, aliases in ALIASES.items():
        if target in dataframe.columns:
            continue

        for alias in aliases:
            original = lowered.get(
                alias.lower()
            )

            if original is not None:
                rename[original] = target
                break

    return dataframe.rename(
        columns=rename
    )


def infer_system(
    path: Path,
    dataframe: pd.DataFrame,
) -> str:
    if (
        "system" in dataframe.columns
        and not dataframe["system"].dropna().empty
    ):
        return str(
            dataframe["system"]
            .dropna()
            .iloc[0]
        ).strip()

    stem = path.stem.lower()

    for system in SYSTEMS:
        if system in stem:
            return system

    mappings = {
        "adaptive": "adaptive_hybrid_graphrag",
        "hybrid": "adaptive_hybrid_graphrag",
        "langchain": "langchain_graphrag",
        "llamaindex": "llamaindex_graphrag",
        "plain": "plain_llm",
        "vector": "vector_rag",
    }

    for key, value in mappings.items():
        if key in stem:
            return value

    return path.stem


def merge_benchmark(
    dataframe: pd.DataFrame,
    benchmark: pd.DataFrame | None,
) -> pd.DataFrame:
    if benchmark is None:
        return dataframe

    dataframe = dataframe.copy()
    benchmark = benchmark.copy()

    dataframe["question_id"] = (
        dataframe["question_id"].astype(str)
    )

    benchmark["question_id"] = (
        benchmark["question_id"].astype(str)
    )

    merged = dataframe.merge(
        benchmark,
        on="question_id",
        how="left",
        suffixes=("", "_benchmark"),
    )

    ground_fields = [
        "question",
        "expected_answer",
        "expected_entities",
        "required_facts",
        "expected_relations",
        "expected_path",
        "gold_evidence",
        "expected_retrieval_route",
        "category",
        "difficulty_level",
    ]

    for field in ground_fields:
        benchmark_field = (
            field + "_benchmark"
        )

        if benchmark_field not in merged:
            continue

        if field in merged:
            merged[field] = merged[
                benchmark_field
            ].combine_first(
                merged[field]
            )
        else:
            merged[field] = merged[
                benchmark_field
            ]

        merged.drop(
            columns=[benchmark_field],
            inplace=True,
        )

    return merged


# --------------------------------------------------------------------------
# WP7: graph-only, vector, and hybrid retrieval-source metrics
# (Guide Section 11)
# --------------------------------------------------------------------------

GRAPH_SOURCE_PREFIX = "graph:"
VECTOR_SOURCE_PREFIX = "vector:"

CYPHER_ERROR_MARKERS = (
    "cyphersyntaxerror",
    "clienterror.statement",
    "cypher_validation_failed",
    "cypher_generation_failed",
    "generated cypher",
)

RELATIONSHIP_PATTERN_RE = re.compile(r"-\[:[A-Za-z_]+.*?\]-\>?|<-\[:[A-Za-z_]+.*?\]-")


def ndcg_at_k(
    gold: list[str],
    retrieved: list[str],
    k: int,
) -> float:
    """
    Binary-relevance nDCG@k. gold_evidence has no graded relevance in this
    benchmark, so a matched item contributes 1.0 (log2-rank discounted)
    and an unmatched item contributes 0.

    IDCG is computed by re-sorting the same per-position relevance labels
    DCG used (the standard construction), not by assuming
    min(len(gold), len(retrieved)) hits are achievable: evidence_match()
    is a fuzzy match, so two distinct (already-deduplicated) retrieved
    strings -- e.g. a graph: item and a vector: item -- can both
    legitimately match the same gold item. Assuming only one hit per gold
    item is possible would let DCG exceed that assumed ceiling and push
    nDCG above 1.0.
    """
    gold_items = uniq(canonical_evidence(item) for item in gold)
    retrieved_items = uniq(canonical_evidence(item) for item in retrieved)[:k]

    if not gold_items:
        return math.nan

    if not retrieved_items:
        return 0.0

    relevance = [
        1.0
        if any(evidence_match(gold_item, item) for gold_item in gold_items)
        else 0.0
        for item in retrieved_items
    ]

    dcg = sum(
        rel / math.log2(rank + 1) for rank, rel in enumerate(relevance, start=1)
    )

    ideal_relevance = sorted(relevance, reverse=True)
    idcg = sum(
        rel / math.log2(rank + 1)
        for rank, rel in enumerate(ideal_relevance, start=1)
    )

    return safe_div(dcg, idcg) if idcg else 0.0


def split_evidence_by_source(
    retrieved_evidence: list[str],
) -> tuple[list[str], list[str]]:
    """
    Split a fused system's retrieved_evidence into (graph_items,
    vector_items) using the graph:/vector: prefix convention from
    src/systems/retrieval_core.py's Evidence.evidence_id. Systems that
    don't use this convention (langchain/llamaindex's raw row dicts,
    vector_rag's unprefixed IDs) return two empty lists, so the per-source
    metrics below correctly come back as "not applicable" rather than a
    misleading zero.
    """
    graph_items: list[str] = []
    vector_items: list[str] = []

    for item in retrieved_evidence:
        item_text = text(item)
        lowered = item_text.lower()

        if lowered.startswith(GRAPH_SOURCE_PREFIX):
            graph_items.append(item_text[len(GRAPH_SOURCE_PREFIX):])
        elif lowered.startswith(VECTOR_SOURCE_PREFIX):
            vector_items.append(item_text[len(VECTOR_SOURCE_PREFIX):])

    return graph_items, vector_items


def hybrid_source_metrics(
    gold_evidence_values: list[str],
    retrieved_evidence_values: list[str],
    k: int,
) -> dict[str, float]:
    """
    Per-source retrieval recall and cross-source overlap/diversity, for
    systems that tag evidence with the graph:/vector: prefix (adaptive
    _hybrid_graphrag, fixed_hybrid_rag, oracle_hybrid_rag). Every field is
    NaN when the row's retrieved_evidence uses neither prefix, since the
    split is then not meaningful for that system.
    """
    graph_items, vector_items = split_evidence_by_source(
        retrieved_evidence_values
    )

    if not graph_items and not vector_items:
        return {
            "graph_source_recall": math.nan,
            "vector_source_recall": math.nan,
            "evidence_source_overlap": math.nan,
            "evidence_source_diversity": math.nan,
        }

    _, graph_recall, _ = retrieval_metrics(gold_evidence_values, graph_items, k)
    _, vector_recall, _ = retrieval_metrics(gold_evidence_values, vector_items, k)

    gold_items = uniq(canonical_evidence(item) for item in gold_evidence_values)
    graph_norm = uniq(canonical_evidence(item) for item in graph_items)
    vector_norm = uniq(canonical_evidence(item) for item in vector_items)

    matched_by_graph = {
        gold_item
        for gold_item in gold_items
        if any(evidence_match(gold_item, item) for item in graph_norm)
    }
    matched_by_vector = {
        gold_item
        for gold_item in gold_items
        if any(evidence_match(gold_item, item) for item in vector_norm)
    }
    matched_by_either = matched_by_graph | matched_by_vector
    matched_by_both = matched_by_graph & matched_by_vector

    overlap = (
        safe_div(len(matched_by_both), len(matched_by_either))
        if matched_by_either
        else math.nan
    )

    return {
        "graph_source_recall": graph_recall,
        "vector_source_recall": vector_recall,
        "evidence_source_overlap": overlap,
        "evidence_source_diversity": float(bool(graph_items) and bool(vector_items)),
    }


def graph_query_quality(row: pd.Series) -> dict[str, float]:
    """
    Invalid/empty-query and hop-count signals for any system that logs
    generated_cypher. NaN when the row never attempted a graph query at
    all, so a vector-only row is never silently counted as "valid."

    graph_hop_count is a heuristic: the number of relationship-pattern
    edges in the generated Cypher text, not a verified traversal depth --
    it will not catch a query that matches the same relationship type
    twice for an unrelated reason. Cross-check against the benchmark's
    reasoning_hops when precision matters.
    """
    cypher = text(row.get("generated_cypher"))

    if not cypher:
        return {
            "graph_query_attempted": 0.0,
            "graph_query_invalid": math.nan,
            "graph_query_empty_result": math.nan,
            "graph_hop_count": math.nan,
        }

    error_text = " ".join(
        [text(row.get("error"))] + flatten(row.get("retrieval_errors"))
    ).lower()

    invalid = float(any(marker in error_text for marker in CYPHER_ERROR_MARKERS))

    if invalid:
        empty_result = math.nan
    else:
        explicit_count = row.get("graph_retrieval_count")

        if explicit_count is not None and not (
            isinstance(explicit_count, float) and math.isnan(explicit_count)
        ):
            try:
                empty_result = float(int(explicit_count) == 0)
            except (TypeError, ValueError):
                empty_result = math.nan
        else:
            # Graph-only systems (langchain/llamaindex/fixed_graph_rag) put
            # the raw graph rows directly in retrieved_evidence.
            empty_result = float(len(flatten(row.get("retrieved_evidence"))) == 0)

    hop_count = float(len(RELATIONSHIP_PATTERN_RE.findall(cypher)))

    return {
        "graph_query_attempted": 1.0,
        "graph_query_invalid": invalid,
        "graph_query_empty_result": empty_result,
        "graph_hop_count": hop_count,
    }


# --------------------------------------------------------------------------
# WP7: abstention-quality classification (Guide Section 12.4)
# --------------------------------------------------------------------------

ABSTENTION_ANSWER_TEXT = "insufficient repository evidence."

# Only the graph/vector/hybrid systems' shared ANSWER prompt instructs the
# model to return ABSTENTION_ANSWER_TEXT verbatim. plain_llm has its own
# prompt (it has no evidence block to plug into ANSWER) that just says to
# "clearly state that the available information is insufficient" without
# specifying exact wording, so its refusals vary ("The available
# information is insufficient to identify...", "I do not have access
# to..."). An exact-match check would misclassify every one of those as a
# confident wrong answer instead of a refusal. Match on the marker phrases
# actually observed instead.
ABSTENTION_MARKERS = (
    "insufficient repository evidence",
    "insufficient",
    "do not have access",
    "does not have access",
    "cannot answer",
    "cannot identify",
    "cannot determine",
    "no way to determine",
    "unable to determine",
    "i don't know",
    "i do not know",
)


def is_abstention_answer(answer: str) -> bool:
    normalized = norm(answer)

    if not normalized:
        return False

    return any(marker in normalized for marker in ABSTENTION_MARKERS)


def row_answerable(row: pd.Series) -> bool:
    """
    Whether the benchmark row is marked answerable. Defaults to True when
    the column is absent (benchmarks generated before WP3's schema
    addition) or empty, since every question in those benchmarks was
    grounded in an executed, non-empty Cypher result.
    """
    value = row.get("answerable")

    if value is None:
        return True

    if isinstance(value, float) and math.isnan(value):
        return True

    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", ""}

    return bool(value)


def classify_abstention_quality(
    *,
    answerable: bool,
    abstained: bool,
    answer_accuracy: float,
) -> str:
    """
    Guide Section 12.4: distinguish a correct refusal from a wasted
    opportunity to answer, and an incorrect confident answer from a
    fabricated one on a genuinely unanswerable question.
    """
    if answerable:
        if abstained:
            return "unnecessary_abstention"

        return "correct_answer" if answer_accuracy >= 1.0 else "incorrect_confident_answer"

    return "correct_abstention" if abstained else "unsupported_answer"


def evaluate_row(
    row: pd.Series,
    system: str,
    k: int,
) -> dict[str, Any]:
    answer = text(row.get("answer"))
    reference = text(
        row.get("expected_answer")
    )
    error = text(row.get("error"))

    expected_entity_values = expected_entities(
        row
    )

    predicted_entity_values = (
        flatten(row.get("predicted_entities"))
        or extract_entities(answer)
    )

    required_fact_values = flatten(
        row.get("required_facts")
    )

    # A benchmark may omit a separate required_facts column. In that case,
    # use the validated reference answer (or explicit expected entities) so the
    # metric remains defined and comparable across all systems.
    if not required_fact_values:
        if reference:
            required_fact_values = [reference]
        else:
            required_fact_values = list(expected_entity_values)

    expected_relation_values = relations(
        row.get("expected_relations")
    )

    predicted_relation_values = relations(
        row.get("predicted_relations")
    )

    expected_path_values = flatten(
        row.get("expected_path")
    )

    predicted_path_values = flatten(
        row.get("predicted_path")
    )

    gold_evidence_values = flatten(
        row.get("gold_evidence")
    )

    retrieved_evidence_values = flatten(
        row.get("retrieved_evidence")
    )

    (
        answer_accuracy,
        ground_truth_coverage,
        matched_entities,
        expected_entity_count,
    ) = coverage(
        answer,
        expected_entity_values,
    )

    (
        entity_precision,
        entity_recall,
        entity_f1,
    ) = set_prf(
        expected_entity_values,
        predicted_entity_values,
    )

    (
        required_fact_coverage,
        matched_fact_count,
        required_fact_count,
    ) = fact_coverage(
        answer,
        required_fact_values,
    )

    if (
        expected_relation_values
        and predicted_relation_values
    ):
        (
            relation_precision,
            relation_recall,
            relation_f1,
        ) = set_prf(
            expected_relation_values,
            predicted_relation_values,
        )
    else:
        relation_precision = math.nan
        relation_recall = math.nan
        relation_f1 = math.nan

    if (
        expected_path_values
        and predicted_path_values
    ):
        _, path_accuracy, _ = set_prf(
            expected_path_values,
            predicted_path_values,
        )
    else:
        path_accuracy = math.nan

    if (
        len(expected_path_values) >= 2
        and not math.isnan(path_accuracy)
    ):
        multi_hop_completion = path_accuracy
    else:
        multi_hop_completion = math.nan

    support = (
        required_fact_values
        + gold_evidence_values
        + expected_entity_values
    )

    (
        supported_claim_rate,
        hallucination_rate,
        supported_claim_count,
        claim_count,
    ) = grounding(
        answer,
        row.get("generated_claims"),
        support,
        predicted_entity_values,
    )

    (
        evidence_precision,
        evidence_recall,
        mrr,
    ) = retrieval_metrics(
        gold_evidence_values,
        retrieved_evidence_values,
        k,
    )

    ndcg = ndcg_at_k(
        gold_evidence_values,
        retrieved_evidence_values,
        k,
    )

    hybrid_metrics = hybrid_source_metrics(
        gold_evidence_values,
        retrieved_evidence_values,
        k,
    )

    graph_quality = graph_query_quality(row)

    expected_route = norm(
        row.get("expected_retrieval_route")
    )

    selected_route = norm(
        row.get("selected_retrieval_route")
    )

    # Route selection is meaningful only for the adaptive system.
    if (
        system == "adaptive_hybrid_graphrag"
        and expected_route
        and selected_route
    ):
        acceptable_routes = {expected_route}

        if norm(row.get("category")) in {
            "code_retrieval",
            "documentation_lookup",
        }:
            acceptable_routes.update({"vector", "graph", "hybrid"})

        route_accuracy = float(
            selected_route in acceptable_routes
        )
    else:
        route_accuracy = math.nan

    similarity_reference = (
        reference
        or " ".join(expected_entity_values)
    )

    (
        token_precision,
        token_recall,
        token_f1,
    ) = token_prf(
        similarity_reference,
        answer,
    )

    has_answer = bool(answer)
    has_reference = bool(
        reference or expected_entity_values
    )
    is_error = bool(error)

    successful = (
        has_answer
        and has_reference
        and not is_error
    )

    effective_answer_accuracy = answer_accuracy if successful else 0.0

    abstained = is_abstention_answer(answer)
    answerable_flag = row_answerable(row)
    abstention_quality = classify_abstention_quality(
        answerable=answerable_flag,
        abstained=abstained,
        answer_accuracy=effective_answer_accuracy,
    )

    return {
        "question_id": text(
            row.get("question_id")
        ),
        "question": text(
            row.get("question")
        ),
        "category": text(
            row.get("category")
        ),
        "difficulty_level": text(
            row.get("difficulty_level")
        ),
        # reasoning_hops (WP3 benchmark schema) falls back to the older
        # hop_count column for benchmarks generated before that field
        # existed, so the reasoning-depth report table works on either.
        "reasoning_hops": pd.to_numeric(
            row.get("reasoning_hops", row.get("hop_count")),
            errors="coerce",
        ),
        "answer": answer,
        "expected_answer": reference,
        "error": error,
        "has_answer": int(has_answer),
        "has_reference": int(has_reference),
        "is_error": int(is_error),
        "successful": int(successful),
        "answer_accuracy": effective_answer_accuracy,
        "ground_truth_coverage": (
            ground_truth_coverage
            if successful
            else 0.0
        ),
        "matched_reference_count": (
            matched_entities
        ),
        "reference_count": (
            expected_entity_count
        ),
        "entity_precision": (
            entity_precision
            if successful
            else 0.0
        ),
        "entity_recall": (
            entity_recall
            if successful
            else 0.0
        ),
        "entity_f1": (
            entity_f1
            if successful
            else 0.0
        ),
        "required_fact_coverage": (
            required_fact_coverage
        ),
        "matched_fact_count": (
            matched_fact_count
        ),
        "required_fact_count": (
            required_fact_count
        ),
        "relation_precision": (
            relation_precision
        ),
        "relation_recall": (
            relation_recall
        ),
        "relation_f1": relation_f1,
        "path_accuracy": path_accuracy,
        "multi_hop_completion": (
            multi_hop_completion
        ),
        "supported_claim_rate": (
            supported_claim_rate
        ),
        "hallucination_rate": (
            hallucination_rate
        ),
        "supported_claim_count": (
            supported_claim_count
        ),
        "claim_count": claim_count,
        f"evidence_precision_at_{k}": (
            evidence_precision
        ),
        f"evidence_recall_at_{k}": (
            evidence_recall
        ),
        "mrr": mrr,
        "retrieval_route_accuracy": (
            route_accuracy
        ),
        "token_precision": (
            token_precision
            if successful
            else 0.0
        ),
        "token_recall": (
            token_recall
            if successful
            else 0.0
        ),
        "token_f1": (
            token_f1
            if successful
            else 0.0
        ),
        "rouge_l": (
            rouge_l(
                similarity_reference,
                answer,
            )
            if successful
            else 0.0
        ),
        "latency_s": pd.to_numeric(
            row.get("latency_s"),
            errors="coerce",
        ),
        "token_usage": pd.to_numeric(
            row.get("token_usage"),
            errors="coerce",
        ),
        "retrieved_context_tokens": (
            pd.to_numeric(
                row.get(
                    "retrieved_context_tokens"
                ),
                errors="coerce",
            )
        ),
        f"ndcg_at_{k}": ndcg,
        "graph_source_recall": hybrid_metrics["graph_source_recall"],
        "vector_source_recall": hybrid_metrics["vector_source_recall"],
        "evidence_source_overlap": hybrid_metrics["evidence_source_overlap"],
        "evidence_source_diversity": hybrid_metrics["evidence_source_diversity"],
        "graph_query_attempted": graph_quality["graph_query_attempted"],
        "graph_query_invalid": graph_quality["graph_query_invalid"],
        "graph_query_empty_result": graph_quality["graph_query_empty_result"],
        "graph_hop_count": graph_quality["graph_hop_count"],
        "answerable": int(answerable_flag),
        "abstained": int(abstained),
        "abstention_quality": abstention_quality,
        "_bertscore_reference": (
            similarity_reference
        ),
    }


def add_bertscore(
    dataframe: pd.DataFrame,
    model: str,
) -> pd.DataFrame:
    try:
        from bert_score import score
    except ImportError as exc:
        raise RuntimeError(
            "Install BERTScore with: "
            "pip install bert-score"
        ) from exc

    dataframe["bertscore"] = 0.0

    mask = (
        dataframe["successful"].eq(1)
        & dataframe["answer"]
        .astype(str)
        .str.strip()
        .ne("")
        & dataframe["_bertscore_reference"]
        .astype(str)
        .str.strip()
        .ne("")
    )

    if mask.any():
        _, _, f1 = score(
            dataframe.loc[
                mask,
                "answer",
            ].tolist(),
            dataframe.loc[
                mask,
                "_bertscore_reference",
            ].tolist(),
            model_type=model,
            lang="en",
            verbose=True,
        )

        dataframe.loc[
            mask,
            "bertscore",
        ] = f1.cpu().numpy()

    return dataframe


def summarize(
    dataframe: pd.DataFrame,
    k: int,
) -> pd.DataFrame:
    metrics = [
        "answer_accuracy",
        "ground_truth_coverage",
        "entity_precision",
        "entity_recall",
        "entity_f1",
        "required_fact_coverage",
        "relation_precision",
        "relation_recall",
        "relation_f1",
        "path_accuracy",
        "multi_hop_completion",
        "supported_claim_rate",
        "hallucination_rate",
        f"evidence_precision_at_{k}",
        f"evidence_recall_at_{k}",
        f"ndcg_at_{k}",
        "mrr",
        "retrieval_route_accuracy",
        "graph_source_recall",
        "vector_source_recall",
        "evidence_source_overlap",
        "evidence_source_diversity",
        "token_precision",
        "token_recall",
        "token_f1",
        "rouge_l",
    ]

    # Graph query execution quality is meaningful on any row that attempted
    # a graph query, including rows the overall success gate excludes (e.g.
    # an error row still had a graph attempt worth reporting) -- averaged
    # over the full group below, not just successful rows.
    graph_execution_metrics = [
        "graph_query_attempted",
        "graph_query_invalid",
        "graph_query_empty_result",
        "graph_hop_count",
    ]

    abstention_quality_labels = [
        "correct_abstention",
        "unnecessary_abstention",
        "correct_answer",
        "incorrect_confident_answer",
        "unsupported_answer",
    ]

    if "bertscore" in dataframe:
        metrics.append("bertscore")

    output_rows: list[dict[str, Any]] = []

    for system, group in dataframe.groupby(
        "system",
        sort=True,
    ):
        valid = group[
            group["successful"] == 1
        ]

        row: dict[str, Any] = {
            "system": system,
            "total_rows": len(group),
            "successful_rows": int(
                group["successful"].sum()
            ),
            "failed_rows": int(
                (
                    group["successful"] == 0
                ).sum()
            ),
            "error_rows": int(
                group["is_error"].sum()
            ),
            "missing_answer_rows": int(
                (
                    group["has_answer"] == 0
                ).sum()
            ),
            "missing_reference_rows": int(
                (
                    group["has_reference"] == 0
                ).sum()
            ),
            "success_rate": safe_div(
                int(
                    group["successful"].sum()
                ),
                len(group),
            ),
            # Guide Section 12.4 answer_coverage: the fraction of questions
            # the system attempted a real answer for, as opposed to
            # abstaining. Computed over every row, not just "successful"
            # ones, since an abstention still counts as a non-attempt
            # regardless of whether the row was otherwise scorable.
            "answer_coverage": (
                safe_div(
                    int((group["abstained"] == 0).sum()),
                    len(group),
                )
                if "abstained" in group
                else math.nan
            ),
        }

        for metric in metrics + [
            "latency_s",
            "token_usage",
            "retrieved_context_tokens",
        ]:
            if metric not in valid:
                values = pd.Series(
                    dtype=float
                )
            else:
                values = pd.to_numeric(
                    valid[metric],
                    errors="coerce",
                )

            row[metric] = (
                float(values.mean())
                if values.notna().any()
                else math.nan
            )

        # Graph execution quality is averaged over the full group (see
        # graph_execution_metrics comment above), not just successful rows.
        for metric in graph_execution_metrics:
            if metric not in group:
                row[metric] = math.nan
                continue

            values = pd.to_numeric(group[metric], errors="coerce")
            row[metric] = (
                float(values.mean()) if values.notna().any() else math.nan
            )

        # Abstention-quality distribution: fraction of the group's rows
        # falling into each category. Rows are always exactly one category
        # (see classify_abstention_quality), so these five sum to 1.0.
        if "abstention_quality" in group:
            counts = group["abstention_quality"].value_counts()
            total = len(group)

            for label in abstention_quality_labels:
                row[f"abstention_quality_{label}_rate"] = safe_div(
                    int(counts.get(label, 0)), total
                )
        else:
            for label in abstention_quality_labels:
                row[f"abstention_quality_{label}_rate"] = math.nan

        output_rows.append(row)

    return pd.DataFrame(output_rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fair repository-QA evaluation"
        )
    )

    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("results"),
    )

    parser.add_argument(
        "--benchmark-file",
        type=Path,
        default=None,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results"),
    )

    parser.add_argument(
        "--retrieval-k",
        type=int,
        default=10,
    )

    parser.add_argument(
        "--bert-score",
        action="store_true",
    )

    parser.add_argument(
        "--bert-model",
        default="distilbert-base-uncased",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.retrieval_k <= 0:
        raise ValueError(
            "--retrieval-k must be greater than zero"
        )

    files = sorted(
        path
        for path in args.input_dir.resolve().rglob(
            "*.csv"
        )
        if path.name.lower() not in OUTPUTS
    )

    if not files:
        raise FileNotFoundError(
            "No CSV files found under "
            f"{args.input_dir.resolve()}"
        )

    benchmark = None

    if args.benchmark_file:
        benchmark = canonical(
            pd.read_csv(args.benchmark_file)
        )

        if "question_id" not in benchmark:
            raise ValueError(
                "Benchmark must contain question_id"
            )

    frames: list[pd.DataFrame] = []

    for path in files:
        dataframe = canonical(
            pd.read_csv(path)
        )

        if (
            "question_id" not in dataframe
            or "answer" not in dataframe
        ):
            continue

        system = infer_system(
            path,
            dataframe,
        )

        dataframe = merge_benchmark(
            dataframe,
            benchmark,
        )

        evaluated = pd.DataFrame(
            evaluate_row(
                row,
                system,
                args.retrieval_k,
            )
            for _, row in dataframe.iterrows()
        )

        evaluated.insert(
            0,
            "system",
            system,
        )

        evaluated.insert(
            1,
            "source_file",
            str(path),
        )

        frames.append(evaluated)

    if not frames:
        raise RuntimeError(
            "No evaluable CSV files found. "
            "Required columns: question_id and answer"
        )

    per_question = pd.concat(
        frames,
        ignore_index=True,
    )

    print("\nEvaluation input validation")
    print("-" * 100)

    print(
        f"{'System':32} "
        f"{'Rows':>7} "
        f"{'Answers':>9} "
        f"{'Errors':>9} "
        f"{'Missing Ref':>13} "
        f"{'Evaluable':>11}"
    )

    print("-" * 100)

    for system, group in per_question.groupby(
        "system",
        sort=True,
    ):
        print(
            f"{system:32} "
            f"{len(group):>7} "
            f"{int(group['has_answer'].sum()):>9} "
            f"{int(group['is_error'].sum()):>9} "
            f"{int((group['has_reference'] == 0).sum()):>13} "
            f"{int(group['successful'].sum()):>11}"
        )

    if args.bert_score:
        per_question = add_bertscore(
            per_question,
            args.bert_model,
        )

    summary = summarize(
        per_question,
        args.retrieval_k,
    )

    errors = per_question[
        (per_question["successful"] == 0)
        | (per_question["is_error"] == 1)
    ][
        [
            "system",
            "source_file",
            "question_id",
            "question",
            "error",
            "has_answer",
            "has_reference",
            "successful",
        ]
    ]

    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    per_question_path = (
        args.output_dir
        / "per_question_metrics.csv"
    )

    summary_path = (
        args.output_dir
        / "summary_metrics.csv"
    )

    error_path = (
        args.output_dir
        / "evaluation_errors.csv"
    )

    per_question.drop(
        columns=["_bertscore_reference"],
        errors="ignore",
    ).to_csv(
        per_question_path,
        index=False,
    )

    summary.to_csv(
        summary_path,
        index=False,
    )

    errors.to_csv(
        error_path,
        index=False,
    )

    print("\nEvaluation summary")
    print("-" * 180)

    with pd.option_context(
        "display.max_columns",
        None,
        "display.width",
        280,
        "display.float_format",
        lambda value: f"{value:.6f}",
    ):
        print(
            summary.to_string(index=False)
        )

    print("\nMetric interpretation")
    print("-" * 100)
    print(
        "answer_accuracy/entity_f1 : "
        "primary factual correctness"
    )
    print(
        "required_fact_coverage    : "
        "semantic coverage of validated facts"
    )
    print(
        "relation/path metrics     : "
        "reported only when explicit predictions exist"
    )
    print(
        "supported_claim_rate      : "
        "claims supported by benchmark facts/evidence"
    )
    print(
        "hallucination_rate        : "
        "unsupported generated claims"
    )
    print(
        "retrieval metrics         : "
        "canonical evidence matching"
    )
    print(
        "route accuracy            : "
        "reported only for Adaptive Hybrid"
    )
    print(
        "ROUGE-L/BERTScore         : "
        "supporting similarity metrics"
    )

    print("\nOutput files")
    print("-" * 100)
    print(
        "Per-question metrics : "
        f"{per_question_path.resolve()}"
    )
    print(
        "Error report         : "
        f"{error_path.resolve()}"
    )
    print(
        "Summary metrics      : "
        f"{summary_path.resolve()}"
    )

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            f"\nEvaluation failed: {exc}",
            file=sys.stderr,
        )
        raise

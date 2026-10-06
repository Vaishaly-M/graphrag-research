"""Frozen, deterministic entity-based evaluation. See docs/metrics.md for limitations."""
from __future__ import annotations
import json
import math
import re
import statistics
import unicodedata
from collections import defaultdict

from src.evaluation import metrics as legacy


SCHEMA_VERSION = 2
CATEGORY_MAP = {"Structure": "structure", "Code retrieval": "code_retrieval",
                "Dependency analysis": "dependency_analysis", "Documentation lookup": "documentation_lookup",
                "Issue/PR analysis": "issue_pr_analysis", "Developer activity": "developer_activity",
                "Multi-hop reasoning": "multi_hop"}
PATH = re.compile(r"(?<![\w./\\-])(?:[\w.@+-]+[/\\])+[\w.@+/-]+|(?<![\w.-])[\w+-]+\.(?:py|java|js|jsx|ts|tsx|md|rst|txt|json|yaml|yml|xml|properties|cs|go|rs|sh|html|css)\b")
HASH = re.compile(r"(?<![a-fA-F0-9])[a-fA-F0-9]{7,40}(?![a-fA-F0-9])")
EMAIL = re.compile(r"(?:email:)?[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
SYMBOL = re.compile(r"([`'\"])([A-Za-z_][\w.$:<>-]*)\1(?!\s*:)")
NUMBER = re.compile(r"(?<![\w.])#?(\d+)(?![\w.])")
ABSTENTION = re.compile(r"^(?:insufficient (?:repository evidence|information)|not found[.!]?\s*$|no (?:evidence|matching (?:files?|issues?|results?))|(?:i |we )?(?:cannot|can't|am unable to) (?:determine|identify|find))|(?:available|provided) information is insufficient|(?:do not|don't) have (?:access|enough information)|cannot be determined from", re.I)


def value(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    return str(x).strip()


def normalized(x):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value(x))).strip()


def items(x):
    if x is None or value(x) == "":
        return []
    if isinstance(x, (list, tuple)):
        return [value(v) for v in x if value(v)]
    if isinstance(x, str) and x.lstrip().startswith("["):
        parsed = json.loads(x)  # Malformed structured gold is a validation error, never silently coerced.
        if not isinstance(parsed, list):
            raise ValueError("Expected an entity/fact list")
        return [value(v) for v in parsed if value(v)]
    return [value(x)]


def truth(x):
    return value(x).lower() in {"true", "1", "yes"}


def is_abstention(answer):
    return bool(ABSTENTION.search(value(answer)))


def boundary(text, entity, *, insensitive=False):
    """Do not match a path/hash/identifier inside a larger identifier."""
    flags = re.I if insensitive else 0
    token = normalized(entity).replace("\\", "/")
    haystack = normalized(text).replace("\\", "/")
    return bool(token and re.search(r"(?<![\w./:@+-])" + re.escape(token) + r"(?![\w/:@+-]|\.[\w])", haystack, flags))


def entity_kind(row, expected):
    kind = value(row.get("answer_type"))
    if kind:
        return kind
    if expected and all(re.fullmatch(r"#?\d+", e) for e in expected):
        return "issue_number"
    if expected and all(HASH.search(e) for e in expected):
        return "commit_list"
    category = CATEGORY_MAP.get(row.get("category"), row.get("category"))
    if category in {"structure", "code_retrieval", "documentation_lookup", "dependency_analysis", "multi_hop"}:
        return "file_list"
    if category == "issue_pr_analysis":
        return "issue_title_list"
    return "quoted_symbol"


def canonical_entity(entity, kind, gold=()):
    entity = normalized(entity).strip("`\"'")
    if kind in {"file_path", "file_list", "documentation_file"}:
        return entity.replace("\\", "/").removeprefix("./")
    if kind == "issue_number":
        return str(int(entity.lstrip("#"))) if entity.lstrip("#").isdigit() else entity
    if kind == "commit_list":
        matches = HASH.findall(entity)
        if not matches:
            return entity.lower()
        h = matches[-1].lower()
        full = {HASH.findall(g)[-1].lower() for g in gold if HASH.findall(g)}
        candidates = [f for f in full if f.startswith(h)]
        return candidates[0] if len(candidates) == 1 else h
    if kind == "developer_list":
        return entity.removeprefix("email:").lower()
    return entity.casefold()


def matched_entity(answer, entity, kind):
    if kind == "commit_list":
        full = HASH.findall(entity)
        return bool(full and any(full[-1].lower().startswith(h.lower()) for h in HASH.findall(answer)))
    if kind == "developer_list":
        return boundary(answer, entity.removeprefix("email:"), insensitive=True) or boundary(answer, entity, insensitive=True)
    if "|" in entity and kind in {"issue_number_and_title", "issue_title_and_state", "developer_commit_count"}:
        # A composite entity is a relation: components must occur together in one answer line.
        parts = [p.strip() for p in entity.split("|")]
        return any(all(boundary(line, p, insensitive=True) for p in parts) for line in answer.splitlines())
    if kind == "issue_number":
        return canonical_entity(entity, kind) in {str(int(n)) for n in NUMBER.findall(answer)}
    return boundary(answer, entity, insensitive=kind not in {"file_path", "file_list", "documentation_file"})


def extract_entities(answer, row, expected):
    kind = entity_kind(row, expected)
    gold = {canonical_entity(e, kind, expected) for e in expected}
    predicted = {canonical_entity(e, kind, expected) for e in expected if matched_entity(answer, e, kind)}
    if kind in {"file_list", "file_path", "documentation_file"}:
        candidates = [m.group().rstrip(".,;:!?)]}") for m in PATH.finditer(answer)]
        # Repository and question identifiers are context, not extra output files.
        repo = value(row.get("source_repo") or row.get("repo"))
        candidates = [e for e in candidates if e != repo and ":commit:" not in e]
    elif kind == "issue_number":
        candidates = NUMBER.findall(answer)
    elif kind == "commit_list":
        candidates = HASH.findall(answer)
    elif kind == "developer_list":
        candidates = EMAIL.findall(answer)
    elif kind == "quoted_symbol":
        candidates = [m.group(2) for m in SYMBOL.finditer(answer)]
    elif kind == "issue_state":
        candidates = re.findall(r"\b(?:open|closed)\b", answer, flags=re.I)
    else:
        # Titles and composite records have an open vocabulary. Only full gold strings are detected.
        candidates = []
    predicted.update(canonical_entity(e, kind, expected) for e in candidates)
    return kind, gold, predicted


def contradictions(answer, row, expected, kind):
    contradictions_found = []
    # Do not credit explicitly negated required identifiers as an assertion.
    for e in expected:
        if re.search(r"\b(?:not|except|excluding)\s+[`'\"]?" + re.escape(e), answer, re.I):
            contradictions_found.append("negated_expected_entity:" + e)
    # An explicitly asserted unknown commit is a contradiction even for file answers.
    known = HASH.findall(value(row.get("question")) + " " + " ".join(expected))
    known += HASH.findall(" ".join(items(row.get("required_facts"))))
    if known:
        for h in HASH.findall(answer):
            if not any(k.lower().startswith(h.lower()) for k in known):
                contradictions_found.append("unexpected_commit:" + h)
    return contradictions_found


def evaluate_row(row, system=None, k=10):
    system = system or value(row.get("system"))
    answer = value(row.get("answer"))
    expected = items(row.get("expected_entities")) or items(row.get("expected_answer"))
    answerable_value = value(row.get("answerable"))
    answerable = truth(answerable_value) if answerable_value else (True if expected else None)
    error = bool(value(row.get("error")) or value(row.get("error_type")) or
                 value(row.get("retrieval_error")) or items(row.get("retrieval_errors")) or
                 row.get("answer_status") == "error" or not answer)
    abstained = not error and is_abstention(answer)
    kind, gold, predicted = extract_entities(answer, row, expected)
    if kind == "commit_list":
        # Ambiguous short hashes must not satisfy two distinct full gold IDs.
        predicted = {canonical_entity(h, kind, expected) for h in HASH.findall(answer)}
    overlap = len(gold & predicted)
    precision = overlap / len(predicted) if predicted else 0.0
    recall = overlap / len(gold) if gold else None
    f1 = 2 * precision * recall / (precision + recall) if recall is not None and precision + recall else 0.0
    closed = kind in {"file_list", "file_path", "documentation_file", "issue_number", "commit_list", "developer_list", "quoted_symbol", "issue_state"}
    conflicts = contradictions(answer, row, expected, kind)
    scorable = answerable is not None and (not answerable or bool(expected))
    if not scorable:
        strict = None
    elif not answerable:
        strict = int(abstained and not predicted and not conflicts)
    else:
        strict = int(not error and not abstained and gold <= predicted and
                     (not closed or not (predicted - gold)) and not conflicts)
    if error and scorable:
        strict = 0
        precision = recall = f1 = 0.0
    facts = items(row.get("required_facts"))
    checks, unchecked = [], []
    for fact in facts:
        named = [e for e in expected if matched_entity(fact, e, kind)]
        if not named:
            unchecked.append(fact)
        else:
            checks.append(int(not error and not abstained and all(canonical_entity(e, kind, expected) in predicted for e in named)))
    fact_recall = sum(checks) / len(checks) if checks else (recall if not facts else None)
    legacy_accuracy = legacy.coverage(answer, expected)[0] if expected else None
    if error and legacy_accuracy is not None:
        legacy_accuracy = 0.0
    evidence = items(row.get("retrieved_evidence"))[:k]
    evidence_gold = items(row.get("gold_evidence"))
    evidence_metrics = [None, None, None]
    if system != "plain_llm" and value(row.get("selected_retrieval_route")) != "none" and evidence_gold:
        evidence_metrics = list(legacy.retrieval_metrics(evidence_gold, evidence, k))
    return dict(question_id=value(row.get("question_id") or row.get("id")), system=system,
                run_id=row.get("run_id", 1), category=CATEGORY_MAP.get(row.get("category"), row.get("category")),
                source_repo=row.get("source_repo") or row.get("repo"), answerable=answerable,
                scorable=scorable, missing_gold=not scorable, is_error=error, abstained=abstained,
                answer_status="error" if error else "abstained" if abstained else "answered",
                strict_accuracy=strict, legacy_accuracy=legacy_accuracy, fact_recall=fact_recall,
                entity_precision=precision if scorable else None, entity_recall=recall if scorable else None,
                entity_f1=f1 if scorable else None, entity_kind=kind, closed_set=closed,
                predicted_entities=sorted(predicted), missing_entities=sorted(gold-predicted),
                extra_entities=sorted(predicted-gold), contradictions=conflicts,
                unchecked_fact_count=len(unchecked), unchecked_facts=unchecked,
                correct_abstention=int(strict == 1) if answerable is False else None,
                fabrication=int(not error and (not abstained or bool(predicted))) if answerable is False else None,
                evidence_precision_at_k=evidence_metrics[0], evidence_recall_at_k=evidence_metrics[1],
                mrr=evidence_metrics[2], latency_s=row.get("latency_s"),
                total_wall_s=row.get("total_wall_s"), n_attempts=row.get("n_attempts"),
                latency_eligible=truth(row.get("latency_eligible")) and not error,
                superseded=truth(row.get("superseded")), warmup=truth(row.get("warmup")))


def mean(values):
    values = [float(v) for v in values if v is not None and value(v) != "" and not math.isnan(float(v))]
    return statistics.mean(values) if values else None


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        if not truth(row.get("superseded")) and not truth(row.get("warmup")):
            groups[row["system"]].append(row)
    summaries = []
    for system, group in groups.items():
        scorable = [r for r in group if r["scorable"]]
        nonerror = [r for r in scorable if not r["is_error"]]
        latency = [float(r["latency_s"]) for r in group if r["latency_eligible"] and value(r.get("latency_s"))]
        summary = dict(system=system, n_rows=len(group), n_scorable=len(scorable),
                       n_missing_gold=len(group)-len(scorable), n_errors=sum(r["is_error"] for r in group),
                       n_abstained=sum(r["abstained"] for r in group),
                       strict_accuracy=mean(r["strict_accuracy"] for r in scorable),
                       accuracy_non_error=mean(r["strict_accuracy"] for r in nonerror),
                       legacy_accuracy=mean(r["legacy_accuracy"] for r in scorable),
                       abstention_rate=mean(int(r["abstained"]) for r in group if r["answerable"] is True),
                       correct_abstention_rate=mean(r["correct_abstention"] for r in group if r["answerable"] is False),
                       fabrication_rate=mean(r["fabrication"] for r in group if r["answerable"] is False),
                       latency_n=len(latency), latency_mean_s=mean(latency),
                       latency_sd_s=statistics.stdev(latency) if len(latency)>1 else None)
        for key in ["fact_recall", "entity_precision", "entity_recall", "entity_f1", "evidence_precision_at_k", "evidence_recall_at_k", "mrr"]:
            summary[key] = mean(r[key] for r in scorable)
        repeats = defaultdict(list)
        for r in scorable:
            repeats[str(r["run_id"])].append(r["strict_accuracy"])
        repeat_accuracy = [mean(v) for v in repeats.values()]
        summary["accuracy_repeat_mean"] = mean(repeat_accuracy)
        summary["accuracy_repeat_sd"] = statistics.stdev(repeat_accuracy) if len(repeat_accuracy)>1 else None
        summaries.append(summary)
    return summaries

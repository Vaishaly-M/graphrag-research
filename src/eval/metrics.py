"""Pure metrics; no model calls and no substring-based answer matching."""
import math
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Normalization:
    case_sensitive: bool = True
    sha_prefix_length: int = 12

    def __post_init__(self):
        if not 7 <= self.sha_prefix_length <= 40:
            raise ValueError('SHA prefix length must be in [7, 40]')


def normalize(value, config=Normalization()):
    if not isinstance(value, str):
        raise TypeError('Entities must be strings')
    value = unicodedata.normalize('NFC', value).strip()
    issue = re.fullmatch(r'(?:issue\s*#?\s*|#)(\d+)', value, re.I)
    if issue:
        return str(int(issue[1]))
    if re.fullmatch(r'[0-9a-fA-F]{7,40}', value) and re.search('[a-fA-F]', value):
        return value.lower()[:config.sha_prefix_length]
    # Apply only to standalone paths, never to code or prose containing spaces.
    if not re.search(r'\s', value) and ('/' in value or '\\' in value):
        value = value.replace('\\', '/')
        while value.startswith('./'):
            value = value[2:]
    return value if config.case_sensitive else value.casefold()


def entity_sets(predicted, gold, config=Normalization()):
    # Reject full-SHA collisions rather than silently merging distinct commits.
    shas = {v.lower() for v in list(predicted) + list(gold)
            if re.fullmatch('[0-9a-fA-F]{40}', v)}
    prefixes = [v[:config.sha_prefix_length] for v in shas]
    if len(prefixes) != len(set(prefixes)):
        raise ValueError('Ambiguous SHA prefix; increase configured prefix length')
    return {normalize(v, config) for v in predicted}, {normalize(v, config) for v in gold}


def correctness(predicted, gold, *, answerable, abstained=False,
                answer_kind='set', precision_threshold=.8, config=Normalization()):
    if type(answerable) is not bool:
        raise ValueError('Answerability must be verified')
    if not 0 <= precision_threshold <= 1:
        raise ValueError('Invalid precision threshold')
    if answer_kind not in {'set', 'single'}:
        raise ValueError('Unknown answer kind')
    p, g = entity_sets(predicted, gold, config)
    if abstained and p:
        raise ValueError('An abstention cannot contain predicted entities')
    if not answerable:
        return dict(entity_precision=None, entity_recall=None, entity_f1=None,
                    strict_accuracy=int(abstained), lenient_coverage=int(abstained))
    if answer_kind == 'single' and len(g) != 1:
        raise ValueError('Single-value gold must contain exactly one value')
    hits = len(p & g)
    precision = hits / len(p) if p else float(not g)
    recall = hits / len(g) if g else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    strict = p == g if answer_kind == 'single' else recall == 1 and precision >= precision_threshold
    return dict(entity_precision=precision, entity_recall=recall, entity_f1=f1,
                strict_accuracy=int(strict and not abstained),
                lenient_coverage=int(recall == 1 and not abstained))


def retrieval(ranked_ids, gold_ids, k=10):
    if k < 1:
        raise ValueError('k must be positive')
    empty = {f'evidence_recall@{k}': None, 'mrr': None, 'ndcg@10': None}
    if ranked_ids is None or not gold_ids:
        return empty
    gold = set(gold_ids)
    ranked = list(dict.fromkeys(ranked_ids))
    relevant = [int(v in gold) for v in ranked]
    dcg = sum(v / math.log2(i + 2) for i, v in enumerate(relevant[:10]))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(10, len(gold))))
    return {f'evidence_recall@{k}': len(set(ranked[:k]) & gold) / len(gold),
            'mrr': next((1 / (i + 1) for i, v in enumerate(relevant) if v), 0.0),
            'ndcg@10': dcg / ideal}


def score(question, record, precision_threshold=.8, config=Normalization()):
    if not question.get('gold_complete') or (question.get('question_set') == 'H' and
                                            not question.get('human_gold_verified')):
        raise ValueError('Unverified gold cannot be scored')
    metrics = correctness(record['predicted_entities'], question['gold_entities'],
        answerable=question['answerable'], abstained=record['abstained'],
        answer_kind=question.get('answer_kind', 'set'), precision_threshold=precision_threshold,
        config=config)
    if record.get('errors'):
        # An exhausted API failure is not a successful abstention.
        metrics.update(strict_accuracy=0, lenient_coverage=0)
    metrics.update(retrieval(record.get('ranked_evidence_ids'), question['gold_evidence_ids']))
    return metrics


def summarize(records):
    def mean(values):
        values = [v for v in values if v is not None]
        return sum(values) / len(values) if values else None
    keys = sorted({key for r in records for key in r['metrics']})
    result = {key: mean([r['metrics'].get(key) for r in records]) for key in keys}
    result['count'] = len(records)
    result['not_found_rate'] = mean([int(r['abstained'] and not r['errors']) for r in records if not r['answerable']])
    result['over_abstention_rate'] = mean([int(r['abstained'] and not r['errors']) for r in records if r['answerable']])
    clean = [r for r in records if not r['timings']['contaminated'] and not r['errors'] and not r.get('oracle_adaptive_evidence_replay')]
    result['latency_clean_count'] = len(clean)
    result['latency_excluded_count'] = len(records) - len(clean)
    for key in ['retrieval_seconds', 'generation_seconds', 'end_to_end_seconds']:
        result[key] = mean([r['timings'][key] for r in clean])
    result['metric_denominators'] = {key: sum(r['metrics'].get(key) is not None for r in records) for key in keys}
    return result

"""Hooks only: no judge scores are fabricated before Phase 10."""
from typing import Protocol


class ClaimExtractor(Protocol):
    def extract(self, answer: str) -> list[str]: ...


class Judge(Protocol):
    model_family: str
    def judge(self, claim: str, evidence: list[dict]) -> dict: ...


def evaluate(answer, evidence, *, extractor=None, judge=None, generator_families=()):
    if extractor is None or judge is None:
        return {'status': 'not_implemented', 'faithfulness': None, 'unsupported_claim_rate': None}
    families = {v.strip().casefold() for v in generator_families}
    if not families or not judge.model_family.strip() or judge.model_family.strip().casefold() in families:
        raise ValueError('Judge must use a different family from every generator')
    claims = extractor.extract(answer)
    judgments = [judge.judge(c, evidence) for c in claims]
    if any(j.get('label') not in {'supported', 'unsupported', 'uncertain'} for j in judgments):
        raise ValueError('Invalid judge label')
    count = len(claims)
    return dict(status='judged', claims=claims, judgments=judgments,
        faithfulness=sum(j['label'] == 'supported' for j in judgments)/count if count else None,
        unsupported_claim_rate=sum(j['label'] == 'unsupported' for j in judgments)/count if count else None)

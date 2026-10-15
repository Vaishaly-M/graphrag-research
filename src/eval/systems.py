"""Measured adapters. Each transport operation MUST make exactly one attempt."""
import json


class PlainLLM:
    name = 'plain_llm'
    def __init__(self, transport, model):
        self.transport, self.model = transport, model
        self.config = dict(temperature=.2, max_output_tokens=1024, prompt_version='plain-v2-1')

    def answer(self, question, repo, *, timing):
        prompt = ('Answer the repository question using only your knowledge and the question. '
                  'Do not invent repository facts. Return JSON with answer (string), entities '
                  '(array of exact answer values), and abstained (boolean). If you cannot answer, '
                  'use answer="not found", entities=[], abstained=true.\n'
                  f'Repository: {repo}\nQuestion: {question}')
        payload = timing.call('generation', lambda: self.transport(prompt, **self.config))
        parsed = json.loads(payload['text'])
        return dict(answer=parsed['answer'], predicted_entities=parsed['entities'],
                    abstained=parsed['abstained'], ranked_evidence_ids=None, route='none',
                    tokens=payload.get('tokens', {}))


class Stub:
    name, model = 'stub', 'deterministic-stub'
    config = {'version': 1}
    def answer(self, question, repo, *, timing):
        evidence = timing.call('retrieval', lambda: [])
        return timing.call('generation', lambda: dict(answer='not found', predicted_entities=[],
            abstained=True, ranked_evidence_ids=evidence, route='none', tokens={}))


def fixture_transport(prompt, **settings):
    """Offline transport for plumbing tests; never reported as real model evaluation."""
    return {'text': json.dumps(dict(answer='not found', entities=[], abstained=True)), 'tokens': {}}

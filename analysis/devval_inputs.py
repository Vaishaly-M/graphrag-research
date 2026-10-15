"""Resolve only explicit development/validation paths from the split config."""
from src.ingest.storage import ROOT


def input_path(config, question_set, split):
    if question_set not in {'T','P'} or split not in {'development','validation'}:
        raise ValueError('Held-out input is forbidden')
    supplement=config.get('devval_supplement')
    if supplement:
        folder='combined_template' if question_set=='T' else 'paraphrase'
        return ROOT/supplement['directory']/folder/(split+'.jsonl')
    return ROOT/'data/benchmark'/('template' if question_set=='T' else 'paraphrase')/(split+'.jsonl')

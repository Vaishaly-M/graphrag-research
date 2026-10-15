"""Run any measured adapter, with durable resume and gold-blind system inputs."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import time

from .latency import Timing
from .metrics import score, summarize
from .systems import PlainLLM, Stub, fixture_transport


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def read_log(path):
    """Only a torn final line is recoverable; corruption in completed lines is fatal."""
    path = Path(path)
    if not path.exists():
        return []
    data = path.read_bytes()
    lines = data.splitlines(keepends=True)
    rows, valid_bytes = [], 0
    for i, line in enumerate(lines):
        if not line.endswith(b'\n'):
            if i != len(lines)-1:
                raise ValueError('Corrupt run log')
            # No newline means the append was not committed, even if JSON parses.
            with path.open('r+b') as stream:
                stream.truncate(valid_bytes)
            break
        rows.append(json.loads(line))
        valid_bytes += len(line)
    return rows


def append(path, row):
    with Path(path).open('a', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(row, sort_keys=True) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def frozen_revision():
    tags = subprocess.check_output(['git', 'tag', '--points-at', 'HEAD'], text=True).splitlines()
    if not any(t == 'freeze-v2' or t.startswith('freeze-v2.') for t in tags):
        raise ValueError('Test evaluation requires a freeze-v2 tag at HEAD')
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], text=True).strip():
        raise ValueError('Tracked working tree must match freeze tag')
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()


def validate_result(result):
    if not isinstance(result.get('answer'), str) or type(result.get('abstained')) is not bool:
        raise ValueError('Invalid answer record')
    if not isinstance(result.get('predicted_entities'), list) or any(not isinstance(v, str) for v in result['predicted_entities']):
        raise ValueError('Predicted entities must be an explicit string list')
    evidence = result.get('ranked_evidence_ids')
    if evidence is not None and (not isinstance(evidence, list) or any(not isinstance(v, str) for v in evidence)):
        raise ValueError('Ranked evidence must be string IDs or None')
    if result['abstained'] and result['predicted_entities']:
        raise ValueError('Contradictory abstention')


def run(system, questions, output, *, run_id, split, question_set, dry_run=False,
        seed=42, throttle=0.0, precision_threshold=.8, retries=2, backoff=1.0):
    if not run_id or split not in {'development', 'validation', 'test'} or throttle < 0:
        raise ValueError('Invalid run settings')
    if not questions:
        raise ValueError('No questions selected')
    if len({q['question_id'] for q in questions}) != len(questions):
        raise ValueError('Duplicate question IDs')
    for q in questions:
        if q['split'] != split or q['question_set'] != question_set:
            raise ValueError('Sets and splits must be evaluated separately')
        if split != 'test' and (q['repo'] == 'apache/airflow' or q['question_set'] == 'H'):
            raise ValueError('Held-out data in development/validation')
        if not q.get('gold_complete') or (question_set == 'H' and not q.get('human_gold_verified')):
            raise ValueError('Unverified gold excluded')
    revision = frozen_revision() if split == 'test' else None
    # Source hash prevents replay after evaluator/adapter code changes.
    source_files = sorted(Path(__file__).parent.glob('*.py'))
    adapter_file = Path(importlib.import_module(type(system).__module__).__file__)
    source_hash = fingerprint({str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files + [adapter_file]})
    config = dict(system_config=system.config, seed=seed, precision_threshold=precision_threshold,
                  retries=retries, backoff=backoff, throttle=throttle, dry_run=dry_run,
                  source_hash=source_hash, question_hash=fingerprint(questions), freeze_revision=revision)
    config_hash = fingerprint(config)
    identity = dict(system=system.name, model=system.model, config_hash=config_hash,
                    run_id=run_id, split=split, question_set=question_set)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    previous = read_log(output)
    if any(any(r.get(k) != v for k, v in identity.items()) for r in previous):
        raise ValueError('Output belongs to another configuration/run; choose a new output')
    import yaml
    output.with_suffix('.config.yaml').write_text(yaml.safe_dump(dict(identity,config=config),sort_keys=True),encoding='utf-8')
    done = {r['question_id'] for r in previous}
    if len(done) != len(previous):
        raise ValueError('Duplicate records in run log')
    pending = [q for q in questions if q['question_id'] not in done]
    events_path = output.with_suffix('.events.jsonl')
    read_log(events_path)
    for index, q in enumerate(pending):
        # Includes throttle after a resumed question, entirely before timing.
        if throttle and (index or previous):
            time.sleep(throttle)
        timing = Timing(retries=retries, backoff=backoff,
            event_sink=lambda event: append(events_path, dict(identity, question_id=q['question_id'], **event)))
        started = time.perf_counter()
        errors = []
        try:
            result = system.answer(q['question'], q['repo'], timing=timing)
            validate_result(result)
        except Exception as exc:
            errors = [type(exc).__name__]
            result = dict(answer='', predicted_entities=[], abstained=False,
                          ranked_evidence_ids=None, route='error', tokens={})
        wall = time.perf_counter() - started
        record = dict(result, **identity, question_id=q['question_id'], repo=q['repo'],
            answerable=q['answerable'], seed=seed, config=config, dry_run=dry_run,
            timings=timing.result(wall), retries=timing.events, errors=errors,
            cache_key=fingerprint([system.name, system.model, config_hash, q['question_id'], run_id]))
        # Persist raw output before computing metrics, so scoring can always be replayed.
        append(output, record)
    return report(output, questions, precision_threshold=precision_threshold)


def report(output, questions, precision_threshold=.8):
    lookup = {q['question_id']: q for q in questions}
    records = read_log(output)
    scored = [dict(r, metrics=score(lookup[r['question_id']], r, precision_threshold)) for r in records]
    summary = summarize(scored)
    Path(output).with_suffix('.metrics.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    lines = ['# Evaluation metrics', '', 'Offline dry-run plumbing results; not model-quality evidence.' if any(r['dry_run'] for r in records) else 'Computed only from saved raw JSONL.', '', '| Metric | Value |', '|---|---:|']
    lines += [f'| {k} | {v} |' for k, v in summary.items() if not isinstance(v, dict)]
    Path(output).with_suffix('.metrics.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--questions', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--system', default='stub', help='stub, plain_llm (dry-run), or module:factory')
    parser.add_argument('--split', default='development')
    parser.add_argument('--question-set', default='T')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--throttle', type=float, default=0)
    args = parser.parse_args()
    if args.system == 'plain_llm':
        if not args.dry_run:
            parser.error('Supply a module:factory with an explicit one-attempt transport for real calls')
        system = PlainLLM(fixture_transport, 'dry-run-fixture')
    elif args.system == 'stub':
        system = Stub()
    else:
        module, factory = args.system.split(':')
        system = getattr(importlib.import_module(module), factory)()
    questions = [json.loads(line) for line in Path(args.questions).read_text(encoding='utf-8').splitlines() if line.strip()]
    if args.limit is not None:
        if args.limit <= 0:
            parser.error('--limit must be positive')
        questions = questions[:args.limit]
    print(json.dumps(run(system, questions, args.output, run_id=args.run_id, split=args.split,
                        question_set=args.question_set, dry_run=args.dry_run, throttle=args.throttle), indent=2))


if __name__ == '__main__':
    main()

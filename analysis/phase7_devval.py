"""Explicit dev/validation campaign; never loads test or human questions."""
import argparse
import json
import subprocess
import sys
import yaml
from src.ingest.storage import ROOT, read_rows, save, digest
from src.systems.rebuild.engine import NAMES
from analysis.train_router_rebuild import validate_split
from src.eval.metrics import summarize
from analysis.devval_inputs import input_path


def plan():
    config = yaml.safe_load((ROOT/'configs/splits.yaml').read_text())
    jobs = []
    for label, folder in [('T', 'template'), ('P', 'paraphrase')]:
        for split in ['development', 'validation']:
            path = input_path(config,label,split)
            rows = read_rows(path) if path.exists() else []
            if rows:
                validate_split(rows, split, config)
                if any(q['question_set'] != label for q in rows):
                    raise ValueError('Question-set mismatch')
            ready=path.exists()
            if label=='P' and config.get('devval_supplement'):
                manifest=path.with_suffix('.manifest.json')
                source=input_path(config,'T',split)
                metadata=json.loads(manifest.read_text()) if manifest.exists() else {}
                ready=ready and metadata.get('count')==len(rows)==len(read_rows(source)) and metadata.get('source_sha256')==digest(source)
            jobs.append(dict(question_set=label, split=split, count=len(rows), ready=ready,
                             path=str(path.relative_to(ROOT)), sha256=digest(path) if path.exists() else None))
    return jobs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.run_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.run_id):
        parser.error('Use a simple alphanumeric run ID')
    jobs = plan()
    out = ROOT/'runs/phase7'/args.run_id
    save(out/'plan.json', jobs)
    print(json.dumps(jobs, indent=2))
    if not args.execute:
        return
    if not all(job['ready'] for job in jobs):
        raise ValueError('Question generation is incomplete; refusing a partial campaign')
    for name in ['router_v2.json', 'router_v2.sha256', 'vector_selected.yaml']:
        if not (ROOT/'configs'/name).exists():
            raise ValueError('Unfinished prerequisite: '+name)
    # Validate router source/encoder provenance before any paid generation.
    from src.routing.router import RouterV2
    RouterV2()
    summaries = []
    order = [n for n in NAMES if n != 'oracle_hybrid_rag'] + ['oracle_hybrid_rag']
    for job in jobs:
        if not job['count']:
            continue  # Empty P splits are reported, never replaced with P test.
        directory = out/job['question_set']/job['split']
        for system in order:
            if digest(ROOT/job['path']) != job['sha256']:
                raise ValueError('Question input changed during campaign')
            output = directory/(system+'.jsonl')
            command = [sys.executable, '-m', 'src.systems.rebuild.run',
                       '--system', system, '--questions', job['path'],
                       '--split', job['split'], '--question-set', job['question_set'],
                       '--run-id', args.run_id, '--output', str(output)]
            if system == 'oracle_hybrid_rag':
                command += ['--adaptive-results', str(directory/'adaptive_hybrid_graphrag.jsonl')]
            subprocess.run(command, cwd=ROOT, check=True)
            rows = read_rows(output)
            if len(rows) != job['count'] or any(r['errors'] for r in rows):
                raise ValueError('Incomplete/error-containing run; inspect raw JSONL before continuing')
            summaries.append(dict(system=system, question_set=job['question_set'],
                                  split=job['split'], **summarize(rows)))
            save(out/'metrics.json', summaries)
    lines = ['# Phase 7 development/validation', '',
             'Generated from live per-question JSONL. Empty splits have no metrics.', '',
             '| Set | Split | System | N | Strict | Entity F1 | Lenient |',
             '|---|---|---|---:|---:|---:|---:|']
    for row in summaries:
        lines.append('| '+' | '.join(str(row[k]) for k in
            ['question_set','split','system','count','strict_accuracy','entity_f1','lenient_coverage'])+' |')
    lines += ['', 'Input split sizes: '+', '.join(f"{j['question_set']}/{j['split']}={j['count']}" for j in jobs),
              '', 'This report does not authorize freezing; inspect failures and stability first.']
    (out/'metrics.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()

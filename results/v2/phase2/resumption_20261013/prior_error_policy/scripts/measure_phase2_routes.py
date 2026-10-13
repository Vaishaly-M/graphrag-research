"""Fresh uncached Phase 2 timings on accepted router-tuning v2; no templates."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import ROOT, read_jsonl, append_jsonl
from src.evaluation.reproducibility import read_csv, write_csv, sha256, snapshot, save_snapshot, source_hashes
from src.evaluation.harness_v2 import measure_answer
from src.evaluation.metrics_v2 import evaluate_row
from scripts.derive_oracle_routes import ForcedRouter, active_records, clean_timing, atomic_json, ROUTES, quota_stop

OUTPUT = ROOT / 'results/v2/phase2/resumption_20261013'


def measured_oracle(records):
    groups = {}
    for r in records:
        group = groups.setdefault(r['question_id'], {})
        if r['route'] in group:
            raise ValueError('Duplicate active route')
        group[r['route']] = r
    result = []
    for qid, routes in groups.items():
        if set(routes) != set(ROUTES):
            continue
        if not all(clean_timing(r) for r in routes.values()):
            raise ValueError('Unclean timings cannot become Phase 2 labels')
        correct = [r for r in ROUTES if routes[r]['recall_accuracy'] == 1]
        best = min(correct, key=lambda r: (routes[r]['latency_s'], ROUTES.index(r))) if correct else None
        result.append(dict(question_id=qid, oracle_route=best,
            oracle_best_accuracy=max(r['recall_accuracy'] or 0 for r in routes.values()),
            no_route_correct=not correct, cost_policy='minimum clean measured latency'))
    return result


def checkpoint(directory, history, total, status):
    active = active_records(history)
    write_csv(directory/'outcomes.csv', active)
    counts = {}
    for r in active:
        counts.setdefault(r['question_id'], []).append(r)
    progress = dict(status=status, total_questions=total,
        questions_with_all_routes=sum(len(rs)==3 for rs in counts.values()),
        clean_questions=sum(len(rs)==3 and all(clean_timing(r) for r in rs) for rs in counts.values()),
        route_outcomes=len(active), attempts=len(history), errors=sum(bool(r['is_error']) for r in active),
        unclean_outcomes=sum(not clean_timing(r) for r in active),
        resume_command='python -B scripts/measure_phase2_routes.py')
    atomic_json(directory/'progress.json', progress)
    return progress


def main():
    benchmark = ROOT/'data/benchmark/splits_v2/router-tuning.csv'
    policy_path = OUTPUT/'selection_rule.json'
    policy = json.loads(policy_path.read_text())
    if sha256(benchmark) != policy['phase1c_split_sha256']:
        raise RuntimeError('Accepted Phase 1C split changed')
    audit = json.loads((ROOT/'results/v2/phase1c/disjointness.json').read_text())
    if audit['status'] != 'PASS_DETECTABLE_SUBJECTS' or audit['hashes']['router-tuning'] != sha256(benchmark):
        raise RuntimeError('Missing current passing split audit')
    index = ROOT/'results/v2/vector_index'
    manifest = json.loads((index/'manifest.json').read_text())
    if manifest.get('diagnostic_only') or any(sha256(index/n)!=manifest[k] for n,k in
            [('index.faiss','index_sha256'),('docs.json','docs_sha256')]):
        raise RuntimeError('Index verification failed')
    os.environ['VECTOR_INDEX_DIR'] = str(index)
    directory = OUTPUT/'route_outcomes'
    from src.systems.prompts import ADAPTIVE_FINAL_ANSWER, ANSWER_TEMPERATURE, ANSWER_MAX_OUTPUT_TOKENS
    save_snapshot(directory, snapshot(benchmark, 'phase2_clean_forced_routes', mode='no-templates',
        source_hashes=source_hashes(), policy_sha256=sha256(policy_path), cache_enabled=False,
        safety_fallback=False, answer_prompt=ADAPTIVE_FINAL_ANSWER, answer_temperature=ANSWER_TEMPERATURE,
        answer_max_output_tokens=ANSWER_MAX_OUTPUT_TOKENS, evidence_budget_items=16,
        context_token_cap=None, oracle_cost='clean measured latency',
        retry_policy='Stop on any unclean outcome. Explicit next invocation retries it; preserve all attempts.'))
    rows = read_csv(benchmark)
    path = directory/'outcomes.jsonl'
    history = read_jsonl(path)
    ids = {r['question_id'] for r in rows}
    if any(r['question_id'] not in ids or r['route'] not in ROUTES for r in history):
        raise RuntimeError('Unexpected checkpoint membership')
    from src.systems.adaptive_hybrid_graphrag_v2 import System
    from src.systems.adaptive_hybrid_graphrag import AblationConfig
    system = System(router=ForcedRouter('graph'), enable_safety_fallback=False,
                    ablation=AblationConfig(no_templates=True))
    try:
        system.vector_store.load()
        system.vector_store.model.encode(['retrieval warm-up'], normalize_embeddings=True)
        system.graph.query('RETURN 1 AS ready')
        system.llm.cache_enabled = False
        active = {(r['question_id'],r['route']):r for r in active_records(history)}
        for row in rows:
            qid = row['question_id']
            for route in ROUTES:
                if (qid,route) in active and clean_timing(active[qid,route]):
                    continue
                attempt = 1+sum(r['question_id']==qid and r['route']==route for r in history)
                append_jsonl(directory/'attempts.jsonl',dict(question_id=qid,route=route,attempt=attempt,status='started'))
                system.router = ForcedRouter(route)
                result, measurement = measure_answer(system,qid,row['question'],attempt_number=attempt,
                    event_path=directory/'llm_events.jsonl')
                metrics = evaluate_row({**row,**result},system.name)
                record = {**row,**result,**metrics}
                record.update(route=route,mode='no-templates',attempt_number=attempt,retry_events=measurement.events)
                record['frozen_set_strict_accuracy'] = record['strict_accuracy']
                if record['gold_complete'] is not True:
                    record['strict_accuracy'] = None
                history.append(record)
                append_jsonl(path,record)
                append_jsonl(directory/'attempts.jsonl',dict(question_id=qid,route=route,attempt=attempt,status=record['answer_status']))
                clean = clean_timing(record)
                progress = checkpoint(directory,history,len(rows),'RUNNING' if clean else 'STOPPED_UNCLEAN_OUTCOME')
                print(qid,route,record['answer_status'],'clean=',clean,'complete=',progress['clean_questions'],flush=True)
                if not clean:
                    print('FAIL: unclean route outcome retained. Training blocked; resume after investigating.',flush=True)
                    return 2 if quota_stop(record) else 1
        labels = measured_oracle(active_records(history))
        if len(labels)!=len(rows):
            raise RuntimeError('Incomplete measured oracle')
        write_csv(directory/'oracle_routes.csv',labels)
        checkpoint(directory,history,len(rows),'COMPLETE_CLEAN')
        return 0
    except BaseException:
        checkpoint(directory,history,len(rows),'INTERRUPTED')
        raise
    finally:
        system.graph.close()


if __name__ == '__main__':
    sys.exit(main())

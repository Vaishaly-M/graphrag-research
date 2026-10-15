"""Routing metrics and cached route replay. No API clients are imported."""
import argparse
from collections import Counter
from pathlib import Path
import numpy as np
from src.ingest.storage import ROOT,read_rows,save
from src.routing.router import ROUTES,policy
from src.eval.metrics import score

TAUS=[round(.55+.05*i,2) for i in range(9)]


def routing_metrics(rows,key='chosen_route'):
    confusion={a:{b:0 for b in ROUTES} for a in ROUTES};categories={}
    for row in rows:
        actual,predicted=row['gold_route'],row[key]
        confusion[actual][predicted]+=1
        counts=categories.setdefault(row['category'],[0,0]);counts[0]+=actual==predicted;counts[1]+=1
    return dict(count=len(rows),accuracy=sum(r['gold_route']==r[key] for r in rows)/len(rows) if rows else None,
        confusion_matrix=confusion,per_category={c:dict(correct=v[0],count=v[1],accuracy=v[0]/v[1]) for c,v in categories.items()},
        class_support=dict(Counter(r['gold_route'] for r in rows)))


def replay(questions,router_rows,candidates):
    """Replay fixed-route raw outputs at all thresholds; errors stay in accuracy."""
    lookup={q['question_id']:q for q in questions}
    if len(lookup)!=len(questions):raise ValueError('Duplicate questions')
    decisions={r['question_id']:r for r in router_rows}
    if set(decisions)!=set(lookup) or len(decisions)!=len(router_rows):raise ValueError('Router/question IDs must match exactly')
    expected={'graph':'fixed_graph_rag','vector':'vector_rag','hybrid':'fixed_hybrid_rag'}
    caches={}
    for route,rows in candidates.items():
        caches[route]={r['question_id']:r for r in rows}
        if set(caches[route])!=set(lookup) or len(rows)!=len(lookup):raise ValueError('Incomplete/duplicate route cache')
        for r in rows:
            q=lookup[r['question_id']]
            if r['repo']!=q['repo'] or r['split']!=q['split'] or r['question_set']!=q['question_set'] or r['system']!=expected[route]:
                raise ValueError('Cache provenance mismatch')
    if set(caches)!=set(ROUTES):raise ValueError('All three route caches required')
    identities={(r['model'],r['run_id'],r.get('dry_run',False)) for rows in candidates.values() for r in rows}
    if len(identities)!=1:raise ValueError('Route caches must share model, run ID and execution mode')
    import json
    shared_fields=['model','temperature','max_output_tokens','answer_prompt_sha256','dataset','vector','graph','fusion']
    configs={json.dumps({k:r['config']['system_config'][k] for k in shared_fields},sort_keys=True)
             for rows in candidates.values() for r in rows}
    if len(configs)!=1:raise ValueError('Route caches have different retrieval/generation configurations')
    results=[]
    for tau in TAUS:
        selected=[]
        for ident,q in lookup.items():
            decision=policy(decisions[ident]['probabilities'],tau)
            record=caches[decision['chosen_route']][ident]
            selected.append(dict(question_id=ident,route=decision['chosen_route'],metrics=score(q,record)))
        results.append(dict(tau=tau,count=len(selected),strict_accuracy=np.mean([r['metrics']['strict_accuracy'] for r in selected]).item(),
                            routes=dict(Counter(r['route'] for r in selected)),selected=selected))
    return results


def main():
    p=argparse.ArgumentParser();p.add_argument('--router-records',required=True);p.add_argument('--questions',required=True)
    p.add_argument('--output',required=True);p.add_argument('--graph-cache');p.add_argument('--vector-cache');p.add_argument('--hybrid-cache')
    a=p.parse_args();questions=read_rows(ROOT/a.questions)
    if any(q['split']=='test' for q in questions):
        from src.eval.harness import frozen_revision
        frozen_revision()
    if not questions or len({(q['split'],q['question_set']) for q in questions})!=1:raise ValueError('One nonempty set/split per report')
    decisions=read_rows(ROOT/a.router_records);lookup={q['question_id']:q for q in questions}
    if len(decisions)!=len(lookup) or {r['question_id'] for r in decisions}!=set(lookup):raise ValueError('Decision IDs mismatch')
    for row in decisions:
        q=lookup[row['question_id']]
        if row['gold_route']!=q['gold_route'] or row['repo']!=q['repo'] or row['split']!=q['split']:raise ValueError('Routing metadata mismatch')
    report=dict(routing=routing_metrics(decisions),raw_classifier=routing_metrics(decisions,'predicted_route'))
    paths=[a.graph_cache,a.vector_cache,a.hybrid_cache]
    if any(paths):
        if not all(paths):raise ValueError('Supply all three caches')
        report['threshold_sweep']=replay(questions,decisions,{r:read_rows(ROOT/path) for r,path in zip(ROUTES,paths)})
    save(ROOT/a.output,report)


if __name__=='__main__':main()

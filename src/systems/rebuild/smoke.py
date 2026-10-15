"""Five development questions per system; dry-run retains real framework orchestration."""
import argparse
import json
import yaml
from src.ingest.storage import ROOT,read_rows,save
from src.eval.harness import run
from .engine import NAMES,System,configuration,write_configs,best_of_three
from .shared import Gemini,Graph,scoped_cypher


class FixtureLLM:
    model='offline-fixture'
    def __init__(self):self.tokens=[]
    def generate(self,prompt,timing,stage='generation'):
        if stage=='retrieval':
            return timing.call(stage,lambda:'MATCH (f:DLFile) RETURN [f.id] AS evidence_ids, f.path AS text LIMIT 5')
        return timing.call(stage,lambda:json.dumps(dict(answer='not found',entities=[],abstained=True)))


class FixtureGraph:
    def execute(self,query,repo,timing,params=None):
        scoped_cypher(query)
        return timing.call('retrieval',lambda:[dict(id='rebuild:fixture:'+repo+':file:example.py',repo=repo,text='Example fixture file',source='graph')])
    def close(self):pass


class FixtureVector:
    def retrieve(self,question,repo,timing):
        return timing.call('retrieval',lambda:([dict(id='rebuild:fixture:'+repo+':file:readme',repo=repo,text='Example fixture document',source='vector')],['vector:fixture']))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--run-id',required=True);parser.add_argument('--throttle',type=float,default=7)
    args=parser.parse_args()
    questions=read_rows(ROOT/'data/benchmark/template/development.jsonl')[:5]
    assert all(q['split']=='development' and q['repo']!='apache/airflow' for q in questions)
    selected=ROOT/'configs/vector_selected.yaml'
    vector_config=yaml.safe_load(selected.read_text()) if selected.exists() else None
    write_configs(vector_config)
    if args.dry_run:llm,graph,vector=FixtureLLM(),FixtureGraph(),FixtureVector()
    else:
        if vector_config is None:raise ValueError('Development vector grid must finish before live smoke')
        from .vector import VectorRetriever
        directory=ROOT/'data/indexes/vector-development'/str(vector_config['chunk_size'])
        llm,graph=Gemini(),Graph();vector=VectorRetriever(directory,vector_config)
    root=ROOT/'runs/phase5'/args.run_id;root.mkdir(parents=True,exist_ok=True)
    summary=[];outputs={}
    try:
        for name in [n for n in NAMES if n!='oracle_hybrid_rag']+['oracle_hybrid_rag']:
            config=configuration(name,vector_config);config['dry_run']=args.dry_run
            compared=None
            if name=='oracle_hybrid_rag':
                adaptive=outputs['adaptive_hybrid_graphrag']
                if any(r['errors'] for r in adaptive.values()):raise ValueError('Adaptive comparison failed; cannot supply exact evidence')
                compared={(q['repo'],q['question']):adaptive[q['question_id']]['retrieved_evidence'] for q in questions}
                from src.ingest.storage import digest
                config['adaptive_source_sha256']=digest(root/'adaptive_hybrid_graphrag.jsonl')
            system=System(name,graph,vector,llm,config=config,
                          oracle_routes={(q['repo'],q['question']):q['gold_route'] for q in questions} if name=='oracle_hybrid_rag' else None,
                          adaptive_evidence=compared)
            path=root/(name+'.jsonl')
            metrics=run(system,questions,path,run_id=args.run_id,split='development',question_set='T',
                        dry_run=args.dry_run,throttle=0 if args.dry_run else args.throttle)
            rows=read_rows(path);outputs[name]={r['question_id']:r for r in rows}
            for row in rows:print(name,row['question_id'],' -> '.join(row.get('retrieval_path',[])) or 'question_only',flush=True)
            errors=sum(bool(r['errors']) for r in rows)
            summary.append(dict(system=name,questions=len(rows),passed=len(rows)-errors,errors=errors,
                                strict_accuracy=metrics['strict_accuracy']))
            write_report(summary,args,root)
        oracle=[]
        for q in questions:
            candidates={route:outputs[name][q['question_id']] for route,name in [('graph','fixed_graph_rag'),('vector','vector_rag'),('hybrid','fixed_hybrid_rag')]}
            oracle.append(dict(question_id=q['question_id'],**best_of_three(q,candidates)))
        save(root/'oracle_best_of_three.json',oracle)
    finally:graph.close()
    if any(r['errors'] for r in summary):raise SystemExit('Smoke failures; see raw errors')


def write_report(rows,args,root):
    lines=['# Phase 5 smoke tests','',f'Run: `{args.run_id}`. Mode: {"OFFLINE FIXTURE (real framework orchestration, no quality claim)" if args.dry_run else "LIVE development integration"}.',
           '', '| System | Questions | Passed | Errors |','|---|---:|---:|---:|']
    lines += [f'| {r["system"]} | {r["questions"]} | {r["passed"]} | {r["errors"]} |' for r in rows]
    lines += ['', 'Adaptive uses the explicitly provisional hybrid router until Phase 6. Oracle-Best-of-3 is a post-hoc artifact, not another model call. Raw JSONL, per-run YAML configs and metrics are under '+str(root.relative_to(ROOT))+'.',
              '', 'Passing means all requests returned valid records without operational errors; it does not mean answers were correct.']
    name='phase5_smoke_dry_run.md' if args.dry_run else 'phase5_smoke.md'
    (ROOT/'reports'/name).write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':main()

"""CLI for any rebuilt system and one explicit benchmark set/split."""
import argparse
import yaml
from src.ingest.storage import ROOT,read_rows,digest
from src.eval.harness import run
from .engine import System,NAMES,configuration
from .shared import Gemini,Graph
from .vector import VectorRetriever
from .smoke import FixtureGraph,FixtureLLM,FixtureVector


def main():
    p=argparse.ArgumentParser();p.add_argument('--system',required=True,choices=NAMES)
    p.add_argument('--questions',required=True);p.add_argument('--split',required=True,choices=['development','validation','test'])
    p.add_argument('--question-set',required=True);p.add_argument('--run-id',required=True);p.add_argument('--output',required=True)
    p.add_argument('--dry-run',action='store_true');p.add_argument('--limit',type=int);p.add_argument('--throttle',type=float,default=7)
    p.add_argument('--adaptive-results',help='Matching Adaptive raw JSONL, required by Oracle evidence-superset comparison')
    args=p.parse_args();questions=read_rows(ROOT/args.questions)
    if args.limit:
        if args.limit<1:p.error('limit must be positive')
        questions=questions[:args.limit]
    selected_path=ROOT/'configs/vector_selected.yaml'
    selected=yaml.safe_load(selected_path.read_text()) if selected_path.exists() else None
    if args.dry_run:llm,graph,vector=FixtureLLM(),FixtureGraph(),FixtureVector()
    else:
        llm=Gemini();graph=Graph() if args.system not in {'plain_llm','vector_rag'} else None;vector=None
        if args.system in {'vector_rag','fixed_hybrid_rag','oracle_hybrid_rag','adaptive_hybrid_graphrag'}:
            if selected is None:raise ValueError('Vector development tuning is incomplete')
            if args.split=='test':
                directory=ROOT/selected['full_index_directory']
                if digest(directory/'manifest.json')!=selected['full_index_manifest_sha256']:raise ValueError('Selected index hash changed')
            else:directory=ROOT/'data/indexes/vector-development'/str(selected['chunk_size'])
            vector=VectorRetriever(directory,selected)
    config=configuration(args.system,selected);config['dry_run']=args.dry_run
    oracle={(q['repo'],q['question']):q['gold_route'] for q in questions} if args.system=='oracle_hybrid_rag' else None
    compared=None
    if oracle is not None:
        if not args.adaptive_results:p.error('Oracle requires --adaptive-results from the same set/split/run-id')
        saved=read_rows(ROOT/args.adaptive_results)
        if any(r['system']!='adaptive_hybrid_graphrag' or r['run_id']!=args.run_id or r['split']!=args.split or
               r['question_set']!=args.question_set or r['errors'] or r['model']!=llm.model for r in saved):
            raise ValueError('Adaptive comparison provenance mismatch')
        fields=['model','temperature','max_output_tokens','answer_prompt_sha256','dataset','vector','graph','fusion','implementation_sha256']
        if any(any(r['config']['system_config'][k]!=config[k] for k in fields) for r in saved):raise ValueError('Adaptive retrieval/generation configuration differs')
        lookup={r['question_id']:r for r in saved}
        compared={(q['repo'],q['question']):lookup[q['question_id']]['retrieved_evidence'] for q in questions}
        config['adaptive_source_sha256']=digest(ROOT/args.adaptive_results)
    system=System(args.system,graph,vector,llm,config=config,oracle_routes=oracle,adaptive_evidence=compared)
    try:
        print(run(system,questions,ROOT/args.output,run_id=args.run_id,split=args.split,question_set=args.question_set,
                  dry_run=args.dry_run,throttle=0 if args.dry_run else args.throttle))
        if args.dry_run:
            for row in read_rows(ROOT/args.output):print(row['question_id'],row.get('retrieval_path'),row['errors'])
    finally:
        if graph is not None:graph.close()


if __name__=='__main__':main()

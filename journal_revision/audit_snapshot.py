"""Read-only audit of existing experimental artifacts; no API/database calls."""
import json
from pathlib import Path
import pandas as pd
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.systems.query_registry import match_registered_query

ROOT = Path(__file__).resolve().parents[1]

def main():
    b = pd.read_csv(ROOT / 'data/benchmark/splits/hidden_test_answer_key.csv')
    print('CATEGORIES', b.category.value_counts().to_dict())
    print('REPOSITORIES', b.source_repo.value_counts().to_dict())
    print('PUBLIC_COLUMNS', pd.read_csv(ROOT / 'data/benchmark/splits/hidden_test_questions.csv', nrows=0).columns.tolist())
    ids = set(b.id.astype(str))
    for p in sorted((ROOT / 'results/final_evaluation').glob('*_results.csv')):
        d = pd.read_csv(p)
        actual = set(d.question_id.astype(str))
        print('RUN', p.stem, 'rows', len(d), 'unique', len(actual), 'missing', len(ids-actual), 'extra', len(actual-ids), 'modes', d.get('answer_generation_mode', pd.Series(dtype=str)).value_counts().to_dict())
    for folder in ['results', 'results/final_evaluation_metrics']:
        p = ROOT / folder / 'statistical_tests.csv'
        if p.exists():
            d = pd.read_csv(p)
            x = d[(d.metric == 'latency_s') & (d.system_a == 'adaptive_hybrid_graphrag') & (d.system_b == 'fixed_hybrid_rag')]
            if 'subgroup_column' in x:
                x = x[x.subgroup_column == 'overall']
            print('LATENCY_STATS', folder, x.to_dict('records'))
    for p in sorted((ROOT / 'results/final_evaluation_metrics/report_tables').glob('*.csv')):
        print('TABLE', p.name)
        print(pd.read_csv(p).head(8).to_string(index=False))
    p = ROOT / 'results/final_evaluation_metrics/per_question_metrics.csv'
    m = pd.read_csv(p)
    print('METRIC_ROWS',len(m),m.groupby('system').size().to_dict())
    a = m[m.system=='adaptive_hybrid_graphrag']
    o = m[m.system=='oracle_hybrid_rag']
    delta = a.merge(o,on='question_id',suffixes=('_a','_o'))
    print('ORACLE_DISAGREEMENTS',delta.loc[delta.answer_accuracy_a!=delta.answer_accuracy_o,['question_id','answer_accuracy_a','answer_accuracy_o']].to_dict('records'))
    print('ADAPTIVE_FAILURES',a.loc[a.answer_accuracy<1,['question_id','category','answer_accuracy','entity_f1']].to_dict('records'))
    raw = pd.read_csv(ROOT/'results/final_evaluation/adaptive_hybrid_graphrag_results.csv')
    cols=[c for c in ['question_id','question','answer','selected_retrieval_route','answer_generation_mode','retrieval_errors'] if c in raw]
    cases=raw.loc[raw.question_id.isin(a.loc[a.answer_accuracy<1,'question_id']),cols].to_dict('records')
    for case in cases:
        case['answer_excerpt']=str(case.pop('answer'))[:150]
        match=match_registered_query(case['question'])
        case['current_parsed_params']=match.params if match else None
    print('FAILURE_DETAILS',cases)
    print('REGISTRY_COVERAGE',sum(match_registered_query(q) is not None for q in b.question),'of',len(b))
    joined=a.merge(b[['id','source_repo']],left_on='question_id',right_on='id',suffixes=('','_gold'))
    repo_col='source_repo_gold' if 'source_repo_gold' in joined else 'source_repo'
    print('ADAPTIVE_PER_REPO',joined.groupby(repo_col).answer_accuracy.agg(['count','mean']).to_dict('index'))
    for split in ['dev','validation']:
        d=pd.read_csv(ROOT/f'data/benchmark/splits/{split}.csv')
        print('SPLIT_CATEGORIES',split,d.category.value_counts().to_dict())
    for name in ['adaptive_hybrid_graphrag','oracle_hybrid_rag']:
        d=pd.read_csv(ROOT/f'results/final_evaluation/{name}_results.csv')
        print('ORACLE_CASE',name,d.loc[d.question_id.isin(delta.loc[delta.answer_accuracy_a!=delta.answer_accuracy_o,'question_id']),[c for c in cols if c in d]].to_dict('records'))
    print('ANNOTATORS',list((ROOT/'results').rglob('annotator*.csv')))
    print('PROBES',list((ROOT/'data/benchmark').glob('*unanswerable*')))
    print('GRAPH_NODES',sum(x['count'] for x in json.loads((ROOT/'results/graph_validation_report.json').read_text())['graph_checks']['node_counts']))
    for folder in ['final_evaluation_preview_model_partial','final_evaluation']:
        p=ROOT/f'results/{folder}/vector_rag_results.jsonl'
        rows=[json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
        print('VECTOR',folder,'rows',len(rows),'errors',sum(bool(r.get('error')) for r in rows),'fields',list(rows[0]))
    for p in (ROOT/'results').rglob('*hallucination_annotation.csv'):
        try:
            d=pd.read_csv(p)
        except pd.errors.EmptyDataError:
            print('ANNOTATION',p.relative_to(ROOT).as_posix(),'empty file')
            continue
        print('ANNOTATION',p.relative_to(ROOT).as_posix(),'rows',len(d),'labels_nonempty',{c:int(d[c].notna().sum()) for c in ['supported','unsupported','contradicted','incomplete','irrelevant'] if c in d})

if __name__ == '__main__':
    main()

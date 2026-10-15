"""Matched absent/present entity probes, independent of all human questions."""
import hashlib
import random
from pathlib import PurePosixPath

import yaml

from analysis.benchmark_gold import GoldExecutor
from src.ingest.storage import ROOT, digest, read_rows, write_rows
from src.kg.neo4j_store import connect

QUERIES={
 'issue':('issue_pr','MATCH (r:DLRepository)-[:DL_HAS_ISSUE]->(n:DLIssue) WHERE r.dataset=$dataset AND r.repo=$repo AND n.number=$value RETURN n.title AS entity,n.title AS fact,[r.id,n.id] AS evidence_ids'),
 'directory':('structure',"MATCH (r:DLRepository)-[:DL_CONTAINS_FILE]->(n:DLFile) WHERE r.dataset=$dataset AND r.repo=$repo AND n.path STARTS WITH $value AND NOT substring(n.path,size($value)) CONTAINS '/' RETURN n.path AS entity,n.path AS fact,[r.id,n.id] AS evidence_ids ORDER BY entity LIMIT 10"),
 'developer':('developer_activity','MATCH (n:DLDeveloper)-[:DL_AUTHORED_COMMIT]->(c:DLCommit) WHERE n.dataset=$dataset AND n.repo=$repo AND n.email=$value RETURN c.sha AS entity,c.sha AS fact,[n.id,c.id] AS evidence_ids ORDER BY entity LIMIT 10'),
 'commit':('code_retrieval','MATCH (n:DLCommit)-[:DL_MODIFIED_FILE]->(f:DLFile) WHERE n.dataset=$dataset AND n.repo=$repo AND n.sha=$value RETURN f.path AS entity,f.path AS fact,[n.id,f.id] AS evidence_ids ORDER BY entity LIMIT 10')}


def question(kind,value,repo):
    if kind=='issue':text=f'What is the title of issue #{value}'
    elif kind=='directory':text=f'List the first 10 retained paths in lexicographic order directly in directory {value}'
    elif kind=='developer':text=f'List the first 10 sampled commit SHAs in lexicographic order authored by {value}'
    else:text=f'List the first 10 retained paths in lexicographic order modified by sampled commit {value}'
    return text+f' in the recorded snapshot of repository {repo}. If the named entity is absent, answer "not found".'


def build():
    config=yaml.safe_load((ROOT/'configs/splits.yaml').read_text());dataset=config['dataset_id']
    graph=ROOT/'data/graph_exports'/dataset;nodes=read_rows(graph/'nodes.jsonl');edges=read_rows(graph/'relationships.jsonl')
    lookup={n['id']:n for n in nodes};rng=random.Random(config['seed'])
    combinations=[(repo,kind) for repo in sorted(config['test']['repos']) for kind in QUERIES];rng.shuffle(combinations)
    absent=[];present=[]
    with connect() as driver:
        executor=GoldExecutor(driver,digest(graph/'nodes.jsonl'))
        for i in range(40):
            repo,kind=combinations[i%len(combinations)];members=[n for n in nodes if n['repo']==repo]
            if kind=='issue':choices=sorted(n['number'] for n in members if n['label']=='Issue');missing=max(choices)+1000000+i
            elif kind=='directory':
                choices=sorted({str(PurePosixPath(n['path']).parent)+'/' for n in members if n['label']=='File' and '/' in n['path']})
                missing=f'__absent_probe_seed42_{i}/'
            elif kind=='developer':
                choices=sorted({lookup[e['start']]['email'] for e in edges if e['repo']==repo and e['type']=='AUTHORED_COMMIT'})
                missing=f'absent-probe-seed42-{i}@example.invalid'
            else:
                choices=sorted({lookup[e['start']]['sha'] for e in edges if e['repo']==repo and e['type']=='MODIFIED_FILE'})
                missing=hashlib.sha256(f'absent-commit-42-{repo}-{i}'.encode()).hexdigest()[:40]
            near=choices[(i//len(combinations))%len(choices)]
            category,cypher=QUERIES[kind]
            for answerable,value,collection,code in [(False,missing,absent,'U'),(True,near,present,'N')]:
                params=dict(dataset=dataset,repo=repo,value=value);result=executor.execute(cypher,params)
                if bool(result)!=answerable:raise ValueError('Probe existence assertion failed')
                collection.append(dict(question_id=f'{code}-{i:03d}',question_set=code,pair_id=f'pair-{i:03d}',
                    repo=repo,category=category,hop_count=1,template_id='probe_'+kind,template_family='probe_'+kind,
                    question_group=f'probe:{i}',question=question(kind,value,repo),split='test',
                    snapshot=members[0]['snapshot'],gold_cypher=cypher,gold_cypher_parameters=params,
                    executed_gold_result=result,gold_entities=sorted({str(r['entity']) for r in result}),
                    required_facts=sorted({r['fact'] for r in result}) if answerable else ['not found'],
                    gold_evidence_ids=sorted({e for r in result for e in r['evidence_ids']}),
                    gold_route='graph',answerable=answerable,gold_complete=True,gold_source='executed_neo4j',
                    expected_answer=sorted({str(r['entity']) for r in result}) if answerable else 'not found',seed=config['seed']))
    write_rows(ROOT/'data/benchmark/unanswerable/probes.jsonl',absent)
    write_rows(ROOT/'data/benchmark/unanswerable/near_misses.jsonl',present)
    print('Generated 40 absent probes and 40 matched answerable near-misses')


if __name__=='__main__':build()

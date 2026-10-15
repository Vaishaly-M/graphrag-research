"""Versioned development-only supplement; never opens held-out question files."""
import hashlib
import json
import random
import yaml
from analysis.benchmark_gold import GoldExecutor, record, TEMPLATES
from src.ingest.storage import ROOT, read_rows, write_rows, save, digest
from src.kg.neo4j_store import connect

VERSION = 'devval-supplement-1'
FAMILIES = {
 'development': {
  'commit_file_tail': ('multi_hop', 1, 'hybrid',
   "MATCH (c:DLCommit)-[:DL_MODIFIED_FILE]->(f:DLFile) WHERE c.dataset=$dataset AND c.repo=$repo AND c.sha=$sha AND trim(f.content)<>'' WITH c,f,[line IN split(f.content,'\\n') WHERE trim(line)<>''] AS lines RETURN f.path+': '+trim(last(lines)) AS entity,f.path+': '+trim(last(lines)) AS fact,[c.id,f.id] AS evidence_ids ORDER BY f.path LIMIT 5"),
 },
 'validation': {
  'markdown_headings': ('documentation', 1, 'vector',
   "MATCH (f:DLFile) WHERE f.dataset=$dataset AND f.repo=$repo AND f.path=$path UNWIND split(f.content,'\\n') AS line WITH f,trim(line) AS heading WHERE heading STARTS WITH '#' RETURN DISTINCT heading AS entity,heading AS fact,[f.id] AS evidence_ids ORDER BY entity LIMIT $limit"),
  'author_document_headings': ('multi_hop', 2, 'hybrid',
   "MATCH (d:DLDeveloper)-[:DL_AUTHORED_COMMIT]->(c:DLCommit)-[:DL_MODIFIED_FILE]->(f:DLFile) WHERE d.dataset=$dataset AND d.repo=$repo AND d.id=$developer AND f.path ENDS WITH '.md' UNWIND split(f.content,'\\n') AS line WITH d,c,f,trim(line) AS heading WHERE heading STARTS WITH '#' WITH f,heading,collect(DISTINCT d.id)+collect(DISTINCT c.id) AS ids RETURN f.path+': '+heading AS entity,f.path+': '+heading AS fact,ids+[f.id] AS evidence_ids ORDER BY entity LIMIT 5"),
 }}


def build():
    cfg=yaml.safe_load((ROOT/'configs/splits.yaml').read_text())
    base=ROOT/'data/benchmark'/VERSION
    graph=ROOT/'data/graph_exports'/cfg['dataset_id']
    allowed=set(cfg['development']['repos'])
    # Export contents are repository snapshots, not benchmark questions.
    nodes=[n for n in read_rows(graph/'nodes.jsonl') if n['repo'] in allowed]
    edges=[e for e in read_rows(graph/'relationships.jsonl') if e['repo'] in allowed]
    changed={e['start'] for e in edges if e['type']=='MODIFIED_FILE'}
    authors={e['start'] for e in edges if e['type']=='AUTHORED_COMMIT'}
    heading_files={n['id'] for n in nodes if n['label']=='File' and n['path'].endswith('.md')
                   and any(line.strip().startswith('#') for line in n.get('content','').splitlines())}
    heading_commits={e['start'] for e in edges if e['type']=='MODIFIED_FILE' and e['end'] in heading_files}
    heading_authors={e['start'] for e in edges if e['type']=='AUTHORED_COMMIT' and e['end'] in heading_commits}
    for families in FAMILIES.values():TEMPLATES.update(families)
    with connect() as driver:
        executor=GoldExecutor(driver,digest(graph/'nodes.jsonl'))
        for split,families in FAMILIES.items():
            additions=[]
            for repo in sorted(allowed):
                members=[n for n in nodes if n['repo']==repo]
                snapshot=members[0]['snapshot']
                for family in families:
                    pool=[]
                    for n in members:
                        if family=='commit_file_tail' and n['id'] in changed:
                            pool.append(({'sha':n['sha']},f"For sampled commit {n['sha']} in {repo}, identify the first five modified retained nonempty files ordered by path, and give each path followed by its last nonblank trimmed text line.",[n['sha']]))
                        elif family=='markdown_headings' and n['label']=='File' and n['path'].endswith('.md') and '#' in n.get('content',''):
                            for limit in [3,5]:
                                pool.append(({'path':n['path'],'limit':limit},f"In {n['path']} of {repo}, list the first {limit} distinct trimmed Markdown heading lines beginning with #, sorted lexicographically.",[n['path']]))
                        elif family=='author_document_headings' and n['id'] in heading_authors:
                            name=n.get('email') or n.get('login') or n.get('name')
                            pool.append(({'developer':n['id']},f"For {name} in {repo}, find retained .md files modified by that developer's sampled commits. Return the first five distinct path-and-heading pairs in lexicographic order, using trimmed lines starting with #.",[name]))
                    random.Random(f'42:{VERSION}:{repo}:{family}').shuffle(pool)
                    accepted=[]
                    for params,text,protected in pool:
                        params=dict(params,dataset=cfg['dataset_id'],repo=repo)
                        results=executor.execute(TEMPLATES[family][3],params)
                        if not results:continue
                        row=record(repo,family,params,text+' Use only the recorded snapshot and sampled history.',[repo]+protected,results,split,snapshot,cfg)
                        row.update(benchmark_version=VERSION,question_id='TS1-'+row['question_id'][3:])
                        accepted.append(row)
                        if len(accepted)==2:break
                    if len(accepted)!=2:raise ValueError(f'Insufficient gold: {repo}/{family}')
                    additions.extend(accepted)
                    print(split,repo,family,len(accepted),flush=True)
            write_rows(base/'template'/f'{split}.jsonl',additions)
            original=read_rows(ROOT/'data/benchmark/template'/f'{split}.jsonl')
            write_rows(base/'combined_template'/f'{split}.jsonl',original+additions)
    save(base/'manifest.json',dict(version=VERSION,seed=42,source_sha256=digest(__file__),
         families={s:list(f) for s,f in FAMILIES.items()},repos=sorted(allowed),test_inputs=[],human_inputs=[],
         files={str(p.relative_to(base)):digest(p) for p in base.glob('*/*.jsonl')}))


if __name__=='__main__':build()

"""Seeded benchmark construction. Human files are never inputs to this module."""
import hashlib
import json
import random
from pathlib import PurePosixPath

import yaml

from src.ingest.storage import ROOT, digest, read_rows, save, write_rows
from src.kg.neo4j_store import connect, query

VERSION='benchmark-2'
SCOPE='r.dataset=$dataset AND r.repo=$repo'
FILE='MATCH (r:DLRepository)-[:DL_CONTAINS_FILE]->(f:DLFile) WHERE '+SCOPE
TEMPLATES={
 'directory_listing': ('structure',1,'graph', FILE+" AND f.path STARTS WITH $prefix RETURN f.path AS entity,f.path AS fact,[r.id,f.id] AS evidence_ids ORDER BY entity LIMIT 10"),
 'commit_file': ('code_retrieval',1,'graph', 'MATCH (c:DLCommit)-[:DL_MODIFIED_FILE]->(f:DLFile) WHERE c.dataset=$dataset AND c.repo=$repo AND c.sha=$sha RETURN f.path AS entity,f.path AS fact,[c.id,f.id] AS evidence_ids ORDER BY entity LIMIT 10'),
 'dependency_manifest': ('dependency',1,'vector', FILE+" AND (f.path ENDS WITH 'pom.xml' OR f.path ENDS WITH 'pyproject.toml' OR f.path ENDS WITH 'package.json' OR f.path ENDS WITH '.csproj' OR f.path ENDS WITH 'requirements.txt') AND f.path STARTS WITH $prefix RETURN f.path AS entity,f.path AS fact,[r.id,f.id] AS evidence_ids ORDER BY entity LIMIT 10"),
 'documentation_listing': ('documentation',1,'graph', FILE+" AND f.path STARTS WITH $prefix AND (f.path ENDS WITH '.md' OR f.path ENDS WITH '.rst' OR f.path ENDS WITH '.adoc') RETURN f.path AS entity,f.path AS fact,[r.id,f.id] AS evidence_ids ORDER BY entity LIMIT 10"),
 'issue_state': ('issue_pr',1,'graph', 'MATCH (r:DLRepository)-[:DL_HAS_ISSUE]->(i:DLIssue) WHERE '+SCOPE+' AND i.state=$state RETURN toString(i.number) AS entity,toString(i.number) AS fact,[r.id,i.id] AS evidence_ids ORDER BY i.number LIMIT 10'),
 'developer_history': ('developer_activity',1,'graph', 'MATCH (d:DLDeveloper)-[:DL_AUTHORED_COMMIT]->(c:DLCommit) WHERE d.dataset=$dataset AND d.repo=$repo AND d.id=$developer RETURN c.sha AS entity,c.sha AS fact,[d.id,c.id] AS evidence_ids ORDER BY c.sha LIMIT 10'),
 'directory_contributors': ('multi_hop',2,'graph', 'MATCH (d:DLDeveloper)-[:DL_AUTHORED_COMMIT]->(c:DLCommit)-[:DL_MODIFIED_FILE]->(f:DLFile) WHERE d.dataset=$dataset AND d.repo=$repo AND f.path STARTS WITH $prefix WITH d,collect(DISTINCT c.id)+collect(DISTINCT f.id) AS evidence RETURN coalesce(d.email,d.login,d.name) AS entity,coalesce(d.email,d.login,d.name) AS fact,[d.id]+evidence AS evidence_ids ORDER BY entity LIMIT 10'),
 'extension_summary': ('structure',1,'graph', FILE+" AND f.path STARTS WITH $prefix WITH r,coalesce(f.extension,'') AS extension,count(f) AS total,collect(f.id) AS ids RETURN extension+': '+toString(total) AS entity,extension+': '+toString(total) AS fact,[r.id]+ids AS evidence_ids ORDER BY entity"),
 'file_declarations': ('code_retrieval',1,'vector', FILE+" AND f.path=$path WITH r,f,[line IN split(f.content,'\\n') WHERE trim(line) STARTS WITH 'def ' OR trim(line) STARTS WITH 'class ' OR trim(line) STARTS WITH 'public ' OR trim(line) STARTS WITH 'function ' OR trim(line) STARTS WITH 'export '] AS declarations UNWIND CASE WHEN size(declarations)=0 THEN ['no matching declaration lines'] ELSE declarations[0..5] END AS line RETURN trim(line) AS entity,trim(line) AS fact,[r.id,f.id] AS evidence_ids"),
 'import_lines': ('dependency',1,'vector', FILE+" AND f.path=$path WITH r,f,[line IN split(f.content,'\\n') WHERE trim(line) STARTS WITH 'import ' OR trim(line) STARTS WITH 'from ' OR trim(line) STARTS WITH 'using ' OR trim(line) STARTS WITH '#include' OR trim(line) STARTS WITH 'require('] AS imports UNWIND CASE WHEN size(imports)=0 THEN ['no matching import declarations'] ELSE imports[0..5] END AS line RETURN trim(line) AS entity,trim(line) AS fact,[r.id,f.id] AS evidence_ids"),
 'documentation_line': ('documentation',1,'vector', FILE+" AND f.path=$path RETURN trim(split(f.content,'\\n')[$line]) AS entity,f.path+': '+trim(split(f.content,'\\n')[$line]) AS fact,[r.id,f.id] AS evidence_ids"),
 'pull_author': ('issue_pr',1,'graph', 'MATCH (d:DLDeveloper)-[:DL_AUTHORED_PR]->(p:DLPullRequest) WHERE p.dataset=$dataset AND p.repo=$repo AND p.number=$number RETURN coalesce(d.login,d.email,d.name) AS entity,coalesce(d.login,d.email,d.name) AS fact,[d.id,p.id] AS evidence_ids'),
 'developer_commit_count': ('developer_activity',1,'graph', 'MATCH (d:DLDeveloper)-[:DL_AUTHORED_COMMIT]->(c:DLCommit) WHERE d.dataset=$dataset AND d.repo=$repo AND d.id=$developer RETURN toString(count(DISTINCT c)) AS entity,toString(count(DISTINCT c)) AS fact,collect(DISTINCT d.id)+collect(DISTINCT c.id) AS evidence_ids'),
 'co_changed_files': ('multi_hop',2,'graph', 'MATCH (a:DLFile)<-[:DL_MODIFIED_FILE]-(c:DLCommit)-[:DL_MODIFIED_FILE]->(b:DLFile) WHERE a.dataset=$dataset AND a.repo=$repo AND a.path=$path AND a<>b WITH b,collect(DISTINCT a.id)+collect(DISTINCT c.id) AS evidence RETURN b.path AS entity,b.path AS fact,evidence+[b.id] AS evidence_ids ORDER BY entity LIMIT 10'),
 'peer_author_documentation': ('multi_hop',4,'hybrid', 'MATCH (a:DLFile)<-[:DL_MODIFIED_FILE]-(c:DLCommit)<-[:DL_AUTHORED_COMMIT]-(d:DLDeveloper)-[:DL_AUTHORED_COMMIT]->(other:DLCommit)-[:DL_MODIFIED_FILE]->(b:DLFile) WHERE a.dataset=$dataset AND a.repo=$repo AND a.path=$path AND c<>other AND a<>b WITH b,collect(DISTINCT a.id)+collect(DISTINCT c.id)+collect(DISTINCT d.id)+collect(DISTINCT other.id) AS evidence RETURN b.path AS entity,b.path+\': \'+split(b.content,\'\\n\')[0] AS fact,evidence+[b.id] AS evidence_ids ORDER BY entity LIMIT 5'),
}


def options(repo,family,nodes,edges):
    members=[r for r in nodes if r['repo']==repo];lookup={r['id']:r for r in members}
    fs=[r for r in members if r['label']=='File'];out=[]
    if family in {'co_changed_files','peer_author_documentation'}:
        changed={e['end'] for e in edges if e['repo']==repo and e['type']=='MODIFIED_FILE'}
        fs=[f for f in fs if f['id'] in changed]
    def add(params,text,protected):out.append((params,text+' Use only the recorded snapshot and sampled history.',[repo]+protected))
    prefixes=sorted({''}|{str(PurePosixPath(f['path']).parent)+'/' for f in fs if str(PurePosixPath(f['path']).parent)!='.'})
    if family in {'directory_listing','dependency_manifest','documentation_listing','directory_contributors','extension_summary'}:
        for prefix in prefixes:
            names={'directory_listing':'the first 10 retained file paths in lexicographic order below',
                   'dependency_manifest':'the first 10 retained pom.xml, pyproject.toml, package.json, .csproj or requirements.txt paths in lexicographic order below',
                   'documentation_listing':'the first 10 retained .md, .rst or .adoc paths in lexicographic order below',
                   'directory_contributors':'the first 10 author identities in lexicographic order whose sampled commits modified retained files below',
                   'extension_summary':'each retained file extension and its file count below'}
            add(dict(prefix=prefix),f'For repository {repo}, list {names[family]} directory {prefix or "[repository root]"}.',[prefix] if prefix else [])
    elif family=='commit_file':
        changed={e['start'] for e in edges if e['repo']==repo and e['type']=='MODIFIED_FILE'}
        for cid in sorted(changed):
            sha=lookup[cid]['sha'];add(dict(sha=sha),f'Which first 10 retained paths in lexicographic order were modified by sampled commit {sha} in repository {repo}?',[sha])
    elif family=='issue_state':
        for state in ['open','closed']:add(dict(state=state),f'List the first 10 issue numbers in numeric order with state {state} in the recorded API snapshot of repository {repo}.',[state])
    elif family in {'developer_history','developer_commit_count'}:
        authors={e['start'] for e in edges if e['repo']==repo and e['type']=='AUTHORED_COMMIT'}
        for did in sorted(authors):
            d=lookup[did];name=d.get('email') or d.get('login') or d['name']
            text=(f'List the first 10 sampled commit SHAs in lexicographic order authored by {name} in repository {repo}.' if family=='developer_history' else f'How many distinct sampled commits were authored by {name} in repository {repo}?')
            add(dict(developer=did),text,[name])
    elif family=='pull_author':
        for p in members:
            if p['label']=='PullRequest':add(dict(number=p['number']),f'Who authored pull request #{p["number"]} in the recorded API snapshot of repository {repo}?',[str(p['number'])])
    else:
        for f in fs:
            path=f['path'];params=dict(path=path)
            if family=='file_declarations':
                if not path.endswith(('.py','.java','.cs','.js','.ts','.go','.rb')):continue
                text=f'In {path} of repository {repo}, give the first five trimmed lines beginning with def, class, public, function or export, or state that no matching declaration lines exist.'
            elif family=='import_lines':
                if not path.endswith(('.py','.java','.cs','.js','.ts','.go','.rb','.h','.cpp')):continue
                text=f'In {path} of repository {repo}, give the first five explicit lines beginning with import, from, using, #include or require(, or state that no matching import declarations exist.'
            elif family=='documentation_line':
                hits=[i for i,line in enumerate(f['content'].splitlines()[:40]) if line.strip().startswith(('#','//','/*','"""',"'''",'<!--')) and len(line.strip())>15]
                if not hits:continue
                params['line']=hits[0];text=f'What is the documentation or comment text on line {hits[0]+1} of {path} in repository {repo}?'
            elif family=='co_changed_files':text=f'Which first 10 other retained file paths in lexicographic order were changed in a sampled commit that also changed {path} in repository {repo}?'
            else:text=f'For {path} in repository {repo}, find authors of sampled commits modifying it, then their other sampled commits and other retained files. Give the first five resulting paths in lexicographic order and the first text line of each file.'
            add(params,text,[path])
    return out


class GoldExecutor:
    def __init__(self,driver,source_hash):self.driver=driver;self.source_hash=source_hash
    def execute(self,cypher,params):
        key=hashlib.sha256(json.dumps([self.source_hash,cypher,params],sort_keys=True).encode()).hexdigest()
        path=ROOT/'data/annotations/gold_execution_cache'/(key+'.json')
        if path.exists():return json.loads(path.read_text())['rows']
        rows=[dict(r) for r in query(self.driver,cypher,**params)]
        save(path,dict(source_sha256=self.source_hash,cypher=cypher,parameters=params,rows=rows))
        return rows


def record(repo,family,params,question,protected,results,split,snapshot,config):
    category,hops,route,cypher=TEMPLATES[family]
    ident=hashlib.sha256(json.dumps([VERSION,repo,family,params],sort_keys=True).encode()).hexdigest()[:20]
    entities=sorted({str(r['entity']) for r in results if r.get('entity') is not None})
    return dict(question_id='T2-'+ident,question_set='T',repo=repo,category=category,hop_count=hops,
        template_id=family,template_family=family,question_group=f'{repo}|{family}|{ident}',
        question=question,split=split,snapshot=snapshot,gold_cypher=cypher,gold_cypher_parameters=params,
        gold_entities=entities,required_facts=sorted({str(r['fact']) for r in results}),
        gold_evidence_ids=sorted({i for r in results for i in r['evidence_ids']}),gold_route=route,
        answerable=True,gold_complete=True,gold_source='executed_neo4j',protected_strings=protected,
        seed=config['seed'],benchmark_version=VERSION)


def build_templates():
    config=yaml.safe_load((ROOT/'configs/splits.yaml').read_text());dataset=config['dataset_id']
    graph=ROOT/'data/graph_exports'/dataset;nodes=read_rows(graph/'nodes.jsonl');edges=read_rows(graph/'relationships.jsonl')
    all_rows=[]
    with connect() as driver:
        executor=GoldExecutor(driver,digest(graph/'nodes.jsonl'))
        for split in ['development','validation','test']:
            selected=[]
            for repo in config[split]['repos']:
                snapshot=next(n['snapshot'] for n in nodes if n['repo']==repo)
                for family in config[split]['families']:
                    quota=config.get('family_quotas',{}).get(family,config['questions_per_repo_family'])
                    pool=options(repo,family,nodes,edges)
                    random.Random(f'{config["seed"]}:{repo}:{family}').shuffle(pool)
                    accepted=[]
                    for values,question,protected in pool:
                        params=dict(dataset=dataset,repo=repo,**values)
                        results=executor.execute(TEMPLATES[family][3],params)
                        if not results:continue
                        accepted.append(record(repo,family,params,question,protected,results,split,snapshot,config))
                        if len(accepted)==quota:break
                    if len(accepted)!=quota:raise ValueError(f'Insufficient executed gold: {repo}/{family}')
                    selected.extend(accepted);print(split,repo,family,len(accepted),flush=True)
            path=ROOT/'data/benchmark/template'/f'{split}.jsonl'
            if path.exists():
                previous=read_rows(path)
                if previous and all(r.get('benchmark_version')==VERSION for r in previous) and previous!=selected:
                    raise ValueError('Frozen benchmark-2 membership/gold changed: '+split)
            write_rows(path,selected);all_rows.extend(selected)
    manifest=dict(config_sha256=digest(ROOT/'configs/splits.yaml'),export_sha256=digest(graph/'nodes.jsonl'),
        counts={s:sum(r['split']==s for r in all_rows) for s in ['development','validation','test']},
        membership={s:[r['question_id'] for r in all_rows if r['split']==s] for s in ['development','validation','test']})
    save(ROOT/'data/benchmark/split_manifest.json',manifest)
    save(ROOT/'data/benchmark/template/generation_manifest.json',dict(version=VERSION,seed=config['seed'],
        generator_sha256=digest(__file__),human_inputs=[],gold_source='executed read-only Neo4j queries',
        files_sha256={s:digest(ROOT/'data/benchmark/template'/f'{s}.jsonl') for s in ['development','validation','test']}))


if __name__=='__main__':build_templates()

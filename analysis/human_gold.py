"""Held-out annotation tooling. Never imported by template generation or retrieval."""
import argparse
import csv
import json
import math
import re
from collections import Counter
from pathlib import Path

import yaml

from src.ingest.storage import ROOT, digest, read_rows, save, write_rows
from src.kg.neo4j_store import connect
from analysis.benchmark_gold import GoldExecutor

CATEGORIES={'structure':'structure','code retrieval':'code_retrieval','dependency analysis':'dependency',
 'dependency':'dependency','documentation lookup':'documentation','documentation':'documentation',
 'issue/pr analysis':'issue_pr','issue/pr':'issue_pr','developer activity':'developer_activity',
 'multi-hop':'multi_hop','multi hop':'multi_hop','multi-hop reasoning':'multi_hop'}
ROUTES={'structure':'graph','code_retrieval':'vector','dependency':'hybrid','documentation':'vector',
        'issue_pr':'graph','developer_activity':'graph','multi_hop':'hybrid'}
EVIDENCE_QUERY="""UNWIND $evidence_specs AS spec MATCH (n) WHERE n.dataset=$dataset AND n.repo=$repo AND n.id=spec.id
RETURN n.id AS evidence_id,n.label AS kind,n.path AS path,n.sha AS commit,n.number AS number,
n.title AS title,n.email AS email,n.login AS login,n.name AS name,
spec.offset AS character_offset,substring(coalesce(n.content,n.body,n.message,''),spec.offset,2400) AS excerpt ORDER BY evidence_id"""
FIELDS=['question_id','author_id','repo','category','original_question','supplied_gold_proposal',
 'supplied_evidence','supplied_status','supplied_answerable','supplied_hops_expected','supplied_gold_human_verified',
 'candidate_gold_cypher','candidate_parameters_json','executed_result_json','evidence_pointers_json',
 'proposed_gold_route','proposed_answerable','absence_check_cypher','absence_result_json','proposal_notes',
 'verified answer set','annotator OK?','verified_gold_route','verified_answerable','verified_hop_count',
 'verified_evidence_ids','verified_required_facts','annotator_id','source_sha256','graph_sha256']


def source():
    config=yaml.safe_load((ROOT/'configs/splits.yaml').read_text());spec=config['question_sets']['H']
    path=ROOT/spec['source']
    if digest(path)!=spec['source_sha256']:raise ValueError('Held-out source hash changed')
    with path.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
    assert len(rows)==spec['planned_test_count'] and len({r['question_id'] for r in rows})==len(rows)
    assert len({r['author_persona'] for r in rows})==spec['independent_authors_required']
    confirmation=ROOT/'data/annotations/human_source_verification.json'
    spec['confirmed_source_statuses']=[]
    if confirmation.exists():
        attestation=json.loads(confirmation.read_text(encoding='utf-8'))
        if attestation['source_sha256']!=spec['source_sha256']:raise ValueError('Verification confirmation belongs to another source')
        spec['confirmed_source_statuses']=attestation['confirmed_statuses']
    return config,spec,rows


def words(text):return set(re.findall(r'[a-z_][a-z0-9_]{2,}',text.lower()))


def normalize(config,spec,rows,nodes):
    snapshots={r['repo']:r['snapshot'] for r in nodes}
    out=[]
    for row in rows:
        category=CATEGORIES.get(row['category'].strip().lower(),row['category'].strip().lower().replace(' ','_'))
        if category not in ROUTES:raise ValueError('Unmapped human category: '+row['category'])
        if row['repo'] not in snapshots:raise ValueError('Unknown human repository: '+row['repo'])
        out.append(dict(question_id='H-'+row['question_id'],source_question_id=row['question_id'],question_set='H',
            question=row['question'],original_question=row['question'],author_id=row['author_persona'],
            author_persona=row['author_persona'],independent_author_confirmed=spec['persona_is_author_id'],
            repo=row['repo'],category=category,original_category=row['category'],hop_count=None,
            template_id=None,template_family='human_heldout',question_group='human:'+row['question_id'],
            split='test',snapshot=snapshots[row['repo']],source_sha256=spec['source_sha256'],
            supplied_gold_proposal=row['gold_answer'],supplied_evidence=row.get('evidence',''),
            supplied_status=row.get('status',''),supplied_answerable=row.get('answerable',''),
            supplied_hops_expected=row.get('hops_expected',''),
            supplied_gold_human_verified=row.get('status') in spec.get('confirmed_source_statuses',[]),
            gold_cypher=None,gold_entities=[],required_facts=[],
            gold_evidence_ids=[],gold_route=None,answerable=None,gold_complete=False,human_gold_verified=False,
            eligible=False,expected_answer=None,gold_source='pending_human_verification'))
    return out


def draft():
    config,spec,rows=source();graph=ROOT/'data/graph_exports'/config['dataset_id']/'nodes.jsonl'
    graph_hash=digest(graph);nodes=read_rows(graph);normalized=normalize(config,spec,rows,nodes)
    target=ROOT/'data/annotations/human_verification.csv'
    if target.exists():
        existing=list(csv.DictReader(target.open(encoding='utf-8-sig',newline='')))
        if any(r.get('annotator OK?') or r.get('verified answer set') for r in existing):
            raise ValueError('Refusing to overwrite human annotations')
    # This temporary lexical evidence search is confined to annotation proposals.
    # It has no shared index, training artifact, prompt, or router output.
    terms=set().union(*(words(r['question']+' '+r['supplied_gold_proposal']) for r in normalized))
    document_terms={};df=Counter();by_repo={}
    for node in nodes:
        body=' '.join(str(node.get(k) or '') for k in ['path','content','title','body','message','name','email','login'])
        present=words(body)&terms;document_terms[node['id']]=present;df.update(present)
        by_repo.setdefault(node['repo'],[]).append(node)
    annotations=[]
    with connect() as driver:
        executor=GoldExecutor(driver,graph_hash)
        for item in normalized:
            qwords=words(item['question']);proposal_words=words(item['supplied_gold_proposal'])
            def score(node):
                present=document_terms[node['id']]
                return sum((1 if w in qwords else .3)*math.log(1+len(nodes)/(1+df[w])) for w in present&(qwords|proposal_words))
            candidates=sorted(by_repo[item['repo']],key=lambda n:(-score(n),n['id']))[:8]
            ids=[n['id'] for n in candidates if score(n)>0]
            pointers=[]
            for n in candidates:
                if n['id'] not in ids:continue
                body=n.get('content') or n.get('body') or n.get('message') or ''
                anchors=sorted(document_terms[n['id']]&(qwords|proposal_words),key=lambda w:(w not in qwords,df[w],w))
                offset=next((max(0,body.lower().find(w)-300) for w in anchors if w in body.lower()),0)
                pointers.append(dict(id=n['id'],path=n.get('path'),offset=offset,line=body[:offset].count('\n')+1))
            params=dict(dataset=config['dataset_id'],repo=item['repo'],evidence_specs=pointers)
            result=executor.execute(EVIDENCE_QUERY,params)
            absence_query='';absence=[];proposed='unknown'
            # An empty ranked search never proves unanswerability. Only explicit,
            # exact named-entity lookups can support a draft absence proposal.
            checks=[('DLIssue','number',re.findall(r'\bissue\s*#?\s*(\d+)\b',item['question'],re.I)),
                    ('DLCommit','sha',re.findall(r'\b[0-9a-f]{40}\b',item['question'],re.I)),
                    ('DLDeveloper','email',re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',item['question']))]
            for label,field,values in checks:
                if len(values)!=1:continue
                value=int(values[0]) if field=='number' else values[0]
                absence_query=f'MATCH (n:{label}) WHERE n.dataset=$dataset AND n.repo=$repo AND n.{field}=$value RETURN count(n) AS matches'
                absence=executor.execute(absence_query,dict(dataset=config['dataset_id'],repo=item['repo'],value=value))
                if absence[0]['matches']==0:proposed='false'
                break
            item.update(candidate_evidence_ids=ids,proposed_gold_route=ROUTES[item['category']],
                        proposed_answerable=False if proposed=='false' else None,
                        proposed_expected_answer='not found' if proposed=='false' else None)
            annotations.append(dict(question_id=item['question_id'],author_id=item['author_id'],repo=item['repo'],
                category=item['category'],original_question=item['question'],supplied_gold_proposal=item['supplied_gold_proposal'],
                supplied_evidence=item['supplied_evidence'],supplied_status=item['supplied_status'],
                supplied_answerable=item['supplied_answerable'],supplied_hops_expected=item['supplied_hops_expected'],
                supplied_gold_human_verified=item['supplied_gold_human_verified'],
                candidate_gold_cypher=EVIDENCE_QUERY,candidate_parameters_json=json.dumps(params),
                executed_result_json=json.dumps(result,ensure_ascii=False),evidence_pointers_json=json.dumps(pointers),
                proposed_gold_route=ROUTES[item['category']],proposed_answerable=proposed,
                absence_check_cypher=absence_query,absence_result_json=json.dumps(absence),
                proposal_notes='PROPOSAL ONLY: query retrieves candidate evidence, not a verified answer. Ranking uses question plus supplied unverified prose. Empty search is not proof of absence. Approve or correct answer, route, evidence and answerability. Absence is limited to this bounded snapshot.',
                source_sha256=spec['source_sha256'],graph_sha256=graph_hash))
            print('Human evidence draft',item['question_id'],flush=True)
    write_rows(ROOT/'data/benchmark/human/normalized.jsonl',normalized)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=FIELDS);writer.writeheader();writer.writerows(annotations)
    for split in ['development','validation','test']:
        path=ROOT/'data/benchmark/human'/f'{split}.jsonl'
        if not path.exists():write_rows(path,[])
    save(ROOT/'data/benchmark/human/source_manifest.json',dict(source=spec['source'],sha256=spec['source_sha256'],
        count=len(normalized),authors=dict(Counter(r['author_id'] for r in normalized)),
        original_wording_preserved=True,development_use=False,verified_count=0))


def refresh_source_verification():
    """Apply a source-hash-bound user attestation without changing annotation approvals."""
    _,spec,source_rows=source()
    lookup={r['question_id']:r for r in source_rows}
    path=ROOT/'data/benchmark/human/normalized.jsonl'
    rows=read_rows(path)
    for row in rows:
        original=lookup[row['source_question_id']]
        if row['source_sha256']!=spec['source_sha256'] or row['question']!=original['question']:
            raise ValueError('Normalized source provenance changed')
        row['supplied_gold_human_verified']=original.get('status') in spec['confirmed_source_statuses']
    write_rows(path,rows)
    flags={r['question_id']:r['supplied_gold_human_verified'] for r in rows}
    sheet=ROOT/'data/annotations/human_verification.csv'
    with sheet.open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream);fields=list(reader.fieldnames);annotations=list(reader)
    if 'supplied_gold_human_verified' not in fields:fields.append('supplied_gold_human_verified')
    for row in annotations:
        if row['source_sha256']!=spec['source_sha256']:raise ValueError('Sheet source mismatch')
        row['supplied_gold_human_verified']=flags[row['question_id']]
    with sheet.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(annotations)
    manifest_path=ROOT/'data/benchmark/human/source_manifest.json'
    manifest=json.loads(manifest_path.read_text())
    manifest['supplied_gold_human_verified_count']=sum(flags.values())
    manifest['verification_confirmation_sha256']=digest(ROOT/'data/annotations/human_source_verification.json')
    save(manifest_path,manifest)
    print('Human-verified supplied prose answers:',sum(flags.values()))
    from analysis.benchmark_stats import generate
    generate()


def verified_value(row,key,allowed):
    value=row.get(key,'').strip().lower()
    if value not in allowed:raise ValueError(f'{row["question_id"]}: invalid {key}')
    return value


def ingest(sheet):
    config,spec,_=source();base=read_rows(ROOT/'data/benchmark/human/normalized.jsonl')
    lookup={r['question_id']:r for r in base};graph=ROOT/'data/graph_exports'/config['dataset_id']/'nodes.jsonl'
    graph_hash=digest(graph);nodes={n['id']:n for n in read_rows(graph)};accepted=[];excluded=[];seen=set()
    with Path(sheet).open(encoding='utf-8-sig',newline='') as stream:annotations=list(csv.DictReader(stream))
    for row in annotations:
        ident=row['question_id']
        if ident in seen or ident not in lookup:raise ValueError('Duplicate/unknown human ID: '+ident)
        seen.add(ident);original=lookup[ident]
        for key,expected in [('source_sha256',spec['source_sha256']),('graph_sha256',graph_hash),
                             ('original_question',original['question']),('author_id',original['author_id']),('repo',original['repo'])]:
            if row.get(key)!=expected:raise ValueError('Annotation provenance changed: '+ident+'/'+key)
        if row.get('annotator OK?','').strip().lower() not in {'yes','true','ok','1'}:
            excluded.append(dict(question_id=ident,reason='not_human_verified'));continue
        if not row.get('annotator_id','').strip():raise ValueError('Annotator ID required: '+ident)
        answers=json.loads(row['verified answer set'])
        if not isinstance(answers,list) or not all(isinstance(x,str) for x in answers):raise ValueError('Answer set must be a JSON string array')
        answerable=verified_value(row,'verified_answerable',{'true','false'})=='true'
        route=verified_value(row,'verified_gold_route',{'graph','vector','hybrid'})
        hops=int(row['verified_hop_count'])
        if hops<0:raise ValueError('Hop count cannot be negative')
        evidence=json.loads(row.get('verified_evidence_ids') or '[]')
        if answerable and (not answers or not evidence):raise ValueError('Answerable gold requires answers and verified evidence')
        if any(i not in nodes or nodes[i]['repo']!=original['repo'] for i in evidence):raise ValueError('Evidence outside source repository')
        if not answerable and answers not in ([],['not found']):raise ValueError('Unanswerable expected answer is not found')
        facts=json.loads(row.get('verified_required_facts') or '[]')
        accepted.append(dict(original,gold_entities=sorted(set(answers)) if answerable else [],
            expected_answer=sorted(set(answers)) if answerable else 'not found',required_facts=facts,
            gold_evidence_ids=sorted(set(evidence)),gold_route=route,hop_count=hops,answerable=answerable,
            gold_complete=True,human_gold_verified=True,eligible=True,gold_source='human_verified',
            annotator_id=row['annotator_id'],verification_sheet_sha256=digest(sheet)))
    excluded.extend(dict(question_id=i,reason='missing_annotation_row') for i in lookup if i not in seen)
    write_rows(ROOT/'data/benchmark/human/test.jsonl',accepted)
    save(ROOT/'data/benchmark/human/verification_stats.json',dict(source_count=len(base),verified=len(accepted),
        excluded=len(excluded),exclusion_details=excluded,answerable=sum(r['answerable'] for r in accepted),
        category=dict(Counter(r['category'] for r in accepted)),repo=dict(Counter(r['repo'] for r in accepted)),
        gold_route=dict(Counter(r['gold_route'] for r in accepted))))
    from analysis.benchmark_stats import generate
    generate()
    print('Human verified:',len(accepted),'excluded:',len(excluded))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verified-sheet');parser.add_argument('--refresh-source-verification',action='store_true');args=parser.parse_args()
    if args.verified_sheet:ingest(args.verified_sheet)
    elif args.refresh_source_verification:refresh_source_verification()
    else:draft()

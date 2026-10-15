"""Freeze family memberships once and generate counts from actual artifacts."""
import hashlib
import json
import random
from collections import defaultdict
from pathlib import PurePosixPath

import yaml

from src.ingest.storage import ROOT, digest, read_rows, save, write_rows


def candidates(repo, family, nodes, edges):
    lookup={r['id']:r for r in nodes};members=[r for r in nodes if r['repo']==repo]
    fs=[r for r in members if r['label']=='File']
    out=[]
    def add(key,question,answers,evidence):
        if not answers:return
        out.append(dict(question_id='T-'+hashlib.sha256(f'{repo}|{family}|{key}'.encode()).hexdigest()[:20],
            question_set='T',repo=repo,template_family=family,question_group=f'{repo}|{family}|{key}',
            question=question,expected_answer=sorted(set(str(a) for a in answers)),gold_evidence=sorted(set(evidence)),
            snapshot=next(r['snapshot'] for r in members),gold_complete=True,gold_source='canonical_export'))
    if family=='directory_listing':
        groups=defaultdict(list)
        for r in fs:groups[(str(PurePosixPath(r['path']).parent),r['extension'])].append(r)
        for (directory,ext),rs in groups.items():
            add(directory+'|'+ext,f'List the {ext or "extensionless"} files directly in directory {directory} in repository {repo}.',[r['path'] for r in rs],[r['id'] for r in rs])
    if family=='commit_file':
        groups=defaultdict(list)
        for e in edges:
            if e['repo']==repo and e['type']=='MODIFIED_FILE':groups[e['start']].append(e['end'])
        for cid,fids in groups.items():
            add(cid,f'Which retained snapshot files were modified by commit {lookup[cid]["sha"]} in repository {repo}?',[lookup[f]['path'] for f in fids],[cid]+fids)
    if family in {'developer_history','developer_file'}:
        authored=defaultdict(list);modified=defaultdict(list)
        for e in edges:
            if e['repo']!=repo:continue
            if e['type']=='AUTHORED_COMMIT':authored[e['start']].append(e['end'])
            if e['type']=='MODIFIED_FILE':modified[e['start']].append(e['end'])
        for did,cids in authored.items():
            dev=lookup[did]['canonical_id']
            if family=='developer_history':
                add(did,f'List the sampled commit SHAs authored by {dev} in repository {repo}.',[lookup[c]['sha'] for c in cids],[did]+cids)
            else:
                fids=sorted({f for c in cids for f in modified[c]})
                add(did,f'Which retained files were modified through sampled commits authored by {dev} in repository {repo}?',[lookup[f]['path'] for f in fids],[did]+cids+fids)
    if family=='issue_lookup':
        for r in members:
            if r['label']=='Issue':add(r['id'],f'What is the title of issue #{r["number"]} in repository {repo} in the recorded API snapshot?',[r['title']],[r['id']])
    if family=='text_location':
        seen=set()
        for r in fs:
            line=next((x.strip() for x in r['content'].splitlines() if 35<=len(x.strip())<=120),None)
            if not line or line in seen:continue
            seen.add(line)
            matches=[x for x in fs if line in x['content']]
            if len(matches)>5:continue
            add(r['path'],f'Which retained file contains the exact text {json.dumps(line)} in repository {repo}?',[x['path'] for x in matches],[x['id'] for x in matches])
            if len(out)>=50:break
    return out


def build():
    config=yaml.safe_load((ROOT/'configs/splits.yaml').read_text());dataset=config['dataset_id']
    if config.get('benchmark_version')=='benchmark-2':
        from analysis.benchmark_gold import build_templates
        build_templates()
        from analysis.benchmark_stats import generate
        generate()
        return
    graph=ROOT/'data/graph_exports'/dataset
    nodes=read_rows(graph/'nodes.jsonl');edges=read_rows(graph/'relationships.jsonl')
    quota=config['questions_per_repo_family'];summary={};all_rows=[]
    family_sets={s:set(config[s]['families']) for s in ['development','validation','test']}
    assert not family_sets['development']&family_sets['validation']
    assert not (family_sets['development']|family_sets['validation'])&family_sets['test']
    for split in ['development','validation','test']:
        selected=[]
        for repo in config[split]['repos']:
            if split!='test' and repo==config['unseen_repo']:raise ValueError('Unseen repo in tuning config')
            for family in config[split]['families']:
                options=sorted(candidates(repo,family,nodes,edges),key=lambda r:r['question_id'])
                rng=random.Random(f'{config["seed"]}:{repo}:{family}');rng.shuffle(options)
                if len(options)<quota:raise ValueError(f'Insufficient candidates {repo}/{family}: {len(options)} < {quota}')
                selected.extend({**r,'split':split} for r in options[:quota])
        path=ROOT/'data/benchmark/template'/f'{split}.jsonl'
        if path.exists() and read_rows(path)!=selected:raise ValueError('Frozen split membership/content changed: '+split)
        write_rows(path,selected);all_rows.extend(selected)
        summary[split]=len(selected)
        # Empty collection files are explicit absence, not invented paraphrases/human answers.
        for kind in ['paraphrase','human']:
            target=ROOT/'data/benchmark'/kind/f'{split}.jsonl'
            if not target.exists():write_rows(target,[])
    manifest_path=ROOT/'data/benchmark/split_manifest.json'
    manifest=dict(config_sha256=digest(ROOT/'configs/splits.yaml'),export_sha256=digest(graph/'nodes.jsonl'),
        counts=summary,membership={s:[r['question_id'] for r in all_rows if r['split']==s] for s in summary})
    if manifest_path.exists() and json.loads(manifest_path.read_text())!=manifest:raise ValueError('Frozen split manifest changed')
    save(manifest_path,manifest)
    report_counts(config)


def report_counts(config=None):
    config=config or yaml.safe_load((ROOT/'configs/splits.yaml').read_text())
    if config.get('benchmark_version')=='benchmark-2':
        from analysis.benchmark_stats import generate
        generate()
        return
    lines=['# Single source of truth: split counts','','Generated by `python -m analysis.build_splits`. Definitions: `configs/splits.yaml`. Do not hand-edit this table.',
           '', 'Planned counts reserve collection slots. Observed counts count actual question records; eligible counts require collection/gold checks. No P/H examples are fabricated.', '',
           '| Set | Split | Planned | Observed | Eligible | Airflow |','|---|---|---:|---:|---:|---:|']
    errors=[];families=defaultdict(set);ids=set()
    for code,kind in [('T','template'),('P','paraphrase'),('H','human')]:
        for split in ['development','validation','test']:
            path=ROOT/'data/benchmark'/kind/f'{split}.jsonl'
            rows=read_rows(path) if path.exists() else []
            planned=len(config[split]['repos'])*len(config[split]['families'])*config['questions_per_repo_family']
            if code=='H' and config['question_sets']['H']['status']=='pending_user_csv_with_gold':
                planned='Pending upload'
            eligible=0
            authors={r.get('author_id') for r in rows if r.get('independent_author_confirmed')}
            for r in rows:
                if r['question_id'] in ids:errors.append('duplicate ID')
                ids.add(r['question_id']);families[split].add(r['template_family'])
                if r['repo'] not in config[split]['repos'] or r['template_family'] not in config[split]['families']:errors.append('membership violation')
                eligible+=bool(r.get('gold_complete') and (code!='H' or (r.get('human_gold_verified') and len(authors)>=5)))
            airflow=sum(r['repo']==config['unseen_repo'] for r in rows)
            if split!='test' and airflow:errors.append('Airflow leaked into '+split)
            lines.append(f'| {code} | {split} | {planned} | {len(rows)} | {eligible} | {airflow} |')
    if families['development']&families['validation'] or (families['development']|families['validation'])&families['test']:errors.append('family overlap')
    lines.extend(['','## Exact family allocation',''])
    for split in ['development','validation','test']:lines.append(f'- {split}: '+', '.join(config[split]['families']))
    lines.extend(['','Airflow is test-only. Synthetic repository is test-only. Paraphrases inherit source question groups; future H questions require group assignment and five independent authors with human-verified gold.',
                  '', 'Historical splits/results are preserved outside this new data layer and must not be used for the new paper. Prior exposure means the new template pool is not a claim of fully unseen human language.',
                  '', 'Human counts are pending the new CSV with gold answers requested by the user; zero observed is not a completed human benchmark.',
                  '', 'Split validation: '+('PASS' if not errors else 'FAIL: '+', '.join(errors))])
    (ROOT/'reports/split_counts.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    if errors:raise ValueError(errors)


if __name__=='__main__':build()

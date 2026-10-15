"""Qwen-only paraphrases of T test items; no human source access."""
import csv
import hashlib
import json
import random
import re

import requests
import yaml

from src.ingest.storage import ROOT, digest, read_rows, save, write_rows

PROMPT='''Paraphrase this question without answering it. Preserve meaning, scope, requested fields, ordering, limits, and every protected string exactly. Add no hints. Output only the question.
Protected strings: {protected}
Question: {question}
'''
GOLD_FIELDS=['repo','category','hop_count','template_id','gold_cypher','gold_cypher_parameters','gold_entities',
             'required_facts','gold_evidence_ids','gold_route','answerable','snapshot','gold_complete']


def checks(source,question):
    def named(entity,text):return bool(re.search(r'(?<!\w)'+re.escape(entity)+r'(?!\w)',text))
    named_before=[e for e in source['gold_entities'] if named(e,source['question'])]
    protected=sorted(set(source['protected_strings']+re.findall(r'\b\d+\b',source['question'])+named_before))
    missing=[s for s in protected if s not in question]
    return dict(protected_strings=protected,missing_protected=missing,
        gold_entities_named_in_source=named_before,
        missing_previously_named_gold_entities=[e for e in named_before if not named(e,question)],
        gold_entities_not_named_in_paraphrase=[e for e in source['gold_entities'] if not named(e,question)],
        all_gold_entities_named=all(named(e,question) for e in source['gold_entities']))


def build(source=None, output=None):
    supplement=source is not None
    config=yaml.safe_load((ROOT/'configs/splits.yaml').read_text());model=config['question_sets']['P']['model']
    if not model.lower().startswith('qwen'):raise ValueError('Paraphrase provider must be Qwen')
    response=requests.get('http://localhost:11434/api/tags',timeout=15);response.raise_for_status()
    tags={r['name']:r for r in response.json()['models']}
    if model not in tags:raise ValueError('Required Qwen model is not installed')
    model_digest=tags[model]['digest'];source=source or ROOT/'data/benchmark/template/test.jsonl'
    output=output or ROOT/'data/benchmark/paraphrase/test.jsonl'
    templates=read_rows(source)
    if not templates:raise ValueError('Empty template source')
    if supplement and any(r['split'] not in {'development','validation'} or r['repo']=='apache/airflow' or r['question_set']!='T' for r in templates):raise ValueError('Held-out supplement input')
    generation=dict(model=model,model_digest=model_digest,options=dict(seed=42,temperature=.2,num_ctx=2048,num_predict=256,num_thread=8,num_gpu=0))
    out=[]
    for original in templates:
        protected=checks(original,original['question'])['protected_strings']
        prompt=PROMPT.format(protected=json.dumps(protected),question=original['question'])
        key=hashlib.sha256(json.dumps([original,generation,prompt],sort_keys=True).encode()).hexdigest()
        checkpoint=ROOT/'data/benchmark/paraphrase/cache'/(key[:32]+'.json')
        if checkpoint.exists():
            cached=json.loads(checkpoint.read_text());assert cached['key']==key
            question=cached['question'];attempts=cached['attempts']
        else:
            failed=checkpoint.with_suffix('.failed.json')
            prior=json.loads(failed.read_text()) if failed.exists() else {}
            attempts=prior.get('attempts',[]) if prior.get('key')==key else []
            for attempt in range(len(attempts),max(6,len(attempts)+3)):
                actual_prompt=prompt if attempt==0 else prompt+'\nRewrite as a direct question beginning with Which or What. Change the sentence structure: do not copy the original sentence. Preserve all protected strings, scope, and requested fields.\n'
                options=dict(generation['options'],seed=42+attempt)
                response=requests.post('http://localhost:11434/api/generate',json=dict(model=model,prompt=actual_prompt,
                    stream=False,options=options,keep_alive='10m'),timeout=(15,600))
                response.raise_for_status();payload=response.json();question=payload['response'].strip().strip('"')
                check=checks(original,question)
                attempts.append(dict(prompt=actual_prompt,options=options,response=payload,checks=check))
                if not check['missing_protected'] and not check['missing_previously_named_gold_entities'] and question!=original['question'] and payload.get('done_reason')!='length':break
            else:
                save(checkpoint.with_suffix('.failed.json'),dict(key=key,attempts=attempts))
                raise ValueError('Qwen paraphrase failed preservation checks: '+original['question_id'])
            save(checkpoint,dict(key=key,question=question,attempts=attempts,generation=generation))
        check=checks(original,question)
        if check['missing_protected'] or check['missing_previously_named_gold_entities']:raise ValueError('Cached paraphrase failed checks')
        row=dict(original,question_id='P2-'+original['question_id'][3:],question_set='P',question=question,
                 source_question_id=original['question_id'],template_question=original['question'],
                 paraphrase_model=model,paraphrase_model_digest=model_digest,paraphrase_checks=check)
        assert all(row[k]==original[k] for k in GOLD_FIELDS)
        out.append(row);write_rows(output,out)
        print('Paraphrased',len(out),'/',len(templates),flush=True)
    if supplement:
        save(output.with_suffix('.manifest.json'),dict(source_sha256=digest(source),count=len(out),generation=generation,gold_preserved=True,human_inputs=[],test_inputs=[]))
        return
    for split in ['development','validation']:write_rows(ROOT/'data/benchmark/paraphrase'/f'{split}.jsonl',[])
    sample=random.Random(42).sample(out,min(50,len(out)))
    path=ROOT/'data/annotations/paraphrase_spotcheck_50.csv';path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        fields=['question_id','source_question_id','repo','template_question','paraphrase','gold_entities',
                'gold_entities_named_in_source','gold_entities_not_named_in_paraphrase','protected_strings_preserved',
                'meaning preserved?','reviewer notes']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for r in sample:writer.writerow(dict(question_id=r['question_id'],source_question_id=r['source_question_id'],repo=r['repo'],
            template_question=r['template_question'],paraphrase=r['question'],gold_entities=json.dumps(r['gold_entities']),
            gold_entities_named_in_source=json.dumps(r['paraphrase_checks']['gold_entities_named_in_source']),
            gold_entities_not_named_in_paraphrase=json.dumps(r['paraphrase_checks']['gold_entities_not_named_in_paraphrase']),
            protected_strings_preserved=not r['paraphrase_checks']['missing_protected']))
    save(ROOT/'data/benchmark/paraphrase/generation_manifest.json',dict(source_sha256=digest(source),count=len(out),
        generation=generation,prompt_sha256=hashlib.sha256(PROMPT.encode()).hexdigest(),human_inputs=[],
        gold_preserved=True,sample_count=len(sample),complete=True))
    from analysis.benchmark_stats import generate
    generate()


if __name__=='__main__':build()

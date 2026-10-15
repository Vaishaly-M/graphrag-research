"""Generate Qwen paraphrases only for the authorized dev/validation supplement."""
import yaml
import csv
import json
import random
from collections import Counter
from analysis.devval_inputs import input_path
from analysis.paraphrase_questions import build
from src.ingest.storage import ROOT,read_rows


def main():
    config=yaml.safe_load((ROOT/'configs/splits.yaml').read_text())
    if not config.get('devval_supplement'):raise ValueError('Supplement not activated')
    for split in ['development','validation']:
        build(input_path(config,'T',split),input_path(config,'P',split))
    lines=['# Development/validation supplement counts','',
           'Generated from versioned combined files. Existing test/H questions are not read.', '',
           '| Set | Split | Count | Graph | Vector | Hybrid |',
           '|---|---|---:|---:|---:|---:|']
    paraphrases=[]
    for label in ['T','P']:
        for split in ['development','validation']:
            rows=read_rows(input_path(config,label,split))
            routes=Counter(q['gold_route'] for q in rows)
            lines.append(f"| {label} | {split} | {len(rows)} | {routes['graph']} | {routes['vector']} | {routes['hybrid']} |")
            if label=='P':paraphrases.extend(rows)
    (ROOT/'reports/devval_supplement_counts.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    with (ROOT/'data/annotations/devval_paraphrase_spotcheck_50.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        fields=['question_id','split','template_question','question','gold_entities','meaning preserved?']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for q in random.Random(42).sample(paraphrases,min(50,len(paraphrases))):
            writer.writerow({k:json.dumps(q[k]) if k=='gold_entities' else q.get(k,'') for k in fields})


if __name__=='__main__':main()

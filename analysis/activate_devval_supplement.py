"""Validate and activate supplement without changing base or test artifacts."""
from collections import Counter
import yaml
from analysis.devval_supplement import FAMILIES,VERSION
from src.ingest.storage import ROOT,read_rows,digest


def main():
    path=ROOT/'configs/splits.yaml'
    config=yaml.safe_load(path.read_text())
    directory=ROOT/'data/benchmark'/VERSION
    lines=['# Development/validation supplement counts','',
           'Script-generated. Original test files are neither read nor modified.', '',
           '| Set | Split | Total | Graph | Vector | Hybrid |',
           '|---|---|---:|---:|---:|---:|']
    for split,families in FAMILIES.items():
        rows=read_rows(directory/'combined_template'/f'{split}.jsonl')
        expected=set(config[split]['families'])|set(families)
        if any(q['repo'] not in config[split]['repos'] or q['repo']==config['unseen_repo'] or q['split']!=split or q['template_family'] not in expected for q in rows):
            raise ValueError('Invalid supplement membership')
        if len({q['question_id'] for q in rows})!=len(rows):raise ValueError('Duplicate IDs')
        routes=Counter(q['gold_route'] for q in rows)
        if set(routes)!={'graph','vector','hybrid'}:raise ValueError('Missing route class')
        config[split]['families']=[f for f in config[split]['families'] if f not in families]
        lines.append(f"| T | {split} | {len(rows)} | {routes['graph']} | {routes['vector']} | {routes['hybrid']} |")
        lines.append(f"| P (planned) | {split} | {len(rows)} | {routes['graph']} | {routes['vector']} | {routes['hybrid']} |")
    sets=[set(config[s]['families'])|set(FAMILIES.get(s,{})) for s in ['development','validation','test']]
    if any(sets[i]&sets[j] for i in range(3) for j in range(i)):raise ValueError('Family overlap')
    config['devval_supplement']=dict(version=VERSION,directory=str(directory.relative_to(ROOT)).replace('\\','/'),
         manifest_sha256=digest(directory/'manifest.json'),families={s:list(f) for s,f in FAMILIES.items()},authorization='User approved versioned dev/validation supplement')
    path.write_text(yaml.safe_dump(config,sort_keys=False),encoding='utf-8')
    (ROOT/'reports/devval_supplement_counts.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':main()

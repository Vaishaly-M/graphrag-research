"""Train only on development; grouped OOF calibration; select C/tau on validation."""
import argparse
import json
from collections import Counter
from pathlib import Path
import numpy as np
import yaml
from scipy.optimize import minimize_scalar
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GroupKFold

from src.ingest.storage import ROOT,read_rows,save,write_rows,digest
from src.routing.features import NAMES,matrix,features
from src.routing.router import ROUTES,probabilities,policy
from analysis.routing_evaluation import TAUS,routing_metrics
from analysis.devval_inputs import input_path


def validate_split(rows,split,config):
    if not rows:raise ValueError('Empty '+split)
    ids=set()
    for row in rows:
        if row['question_id'] in ids:raise ValueError('Duplicate question ID')
        ids.add(row['question_id'])
        if row['split']!=split or row['question_set'] not in {'T','P'} or row['repo'] not in config[split]['repos'] or row['repo']==config['unseen_repo']:
            raise ValueError('Held-out or incorrectly assigned training/tuning input')
        families=set(config[split]['families'])|set(config.get('devval_supplement',{}).get('families',{}).get(split,[]))
        if row['template_family'] not in families or row['gold_route'] not in ROUTES:raise ValueError('Invalid family or label')
        if row['question_set']=='P' and not row.get('source_question_id'):raise ValueError('Paraphrase parent required')


def fit(x,y,c):
    scaler=StandardScaler().fit(x)
    model=LogisticRegression(C=c,solver='lbfgs',class_weight='balanced',max_iter=2000,random_state=42).fit(scaler.transform(x),y)
    return dict(mean=scaler.mean_.tolist(),scale=scaler.scale_.tolist(),coef=model.coef_.tolist(),
                intercept=model.intercept_.tolist(),classes=model.classes_.tolist(),temperature=1.0)


def log_loss(p,labels):
    return float(np.mean([-np.log(max(row[label],1e-15)) for row,label in zip(p,labels)]))


def train(x,train_rows,x_val,val_rows,allow_missing=False):
    y=np.array([q['gold_route'] for q in train_rows]);groups=np.array([q['repo'] for q in train_rows])
    missing=sorted(set(ROUTES)-set(y))
    if missing and not allow_missing:raise ValueError('Missing training classes: '+','.join(missing))
    if len(set(y))<2:raise ValueError('At least two observed training classes required')
    candidates=[]
    for c in [.1,1.0,10.0]:
        oof=[None]*len(y)
        folds=[]
        for train_idx,cal_idx in GroupKFold(n_splits=len(set(groups))).split(x,y,groups):
            if set(y[train_idx])!=set(y):raise ValueError('A grouped calibration fold lacks an observed class')
            fitted=fit(x[train_idx],y[train_idx],c)
            p=probabilities(x[cal_idx],fitted)
            for index,row in zip(cal_idx,p):oof[index]=row
            folds.append(dict(fit_ids=[train_rows[i]['question_id'] for i in train_idx],calibration_ids=[train_rows[i]['question_id'] for i in cal_idx]))
        # Temperature scaling of held-out-development predictions, never val labels.
        def transformed(temp):
            adjusted=[]
            for row in oof:
                values={r:row[r]**(1/temp) for r in ROUTES};total=sum(values.values())
                adjusted.append({r:v/total for r,v in values.items()})
            return adjusted
        optimum=minimize_scalar(lambda t:log_loss(transformed(t),y),bounds=(.25,4),method='bounded')
        fitted=fit(x,y,c);fitted['temperature']=float(optimum.x)
        p_val=probabilities(x_val,fitted)
        for tau in TAUS:
            rows=[dict(question_id=q['question_id'],category=q['category'],gold_route=q['gold_route'],
                       probabilities=p,**policy(p,tau)) for q,p in zip(val_rows,p_val)]
            candidates.append(dict(C=c,tau=tau,accuracy=routing_metrics(rows)['accuracy'],validation_log_loss=log_loss(p_val,[q['gold_route'] for q in val_rows]),
                temperature=float(optimum.x),calibration_oof_log_loss=log_loss(transformed(optimum.x),y),
                artifact=fitted,folds=folds))
    # Fixed before inspecting validation outcomes: accuracy, log-loss, simpler C, lower tau.
    selected=max(candidates,key=lambda r:(r['accuracy'],-r['validation_log_loss'],-r['C'],-r['tau']))
    return selected,candidates,missing


def main():
    p=argparse.ArgumentParser();p.add_argument('--allow-missing-class',action='store_true');args=p.parse_args()
    config=yaml.safe_load((ROOT/'configs/splits.yaml').read_text())
    paths={s:input_path(config,'T',s) for s in ['development','validation']}
    dev,val=[read_rows(paths[s]) for s in paths]
    # Train on T only (P is optional); never load P/test, H, or T/test.
    validate_split(dev,'development',config);validate_split(val,'validation',config)
    if {q['template_family'] for q in dev}&{q['template_family'] for q in val}:raise ValueError('Family leakage')
    if {q['question_group'] for q in dev}&{q['question_group'] for q in val}:raise ValueError('Question-group leakage')
    if set(ROUTES)-{q['gold_route'] for q in dev} and not args.allow_missing_class:
        raise ValueError('Missing hybrid training class; explicit limitation acceptance or new versioned data required')
    from src.retrieval.embeddings import Encoder
    encoder=Encoder();x=matrix(dev,encoder);xv=matrix(val,encoder)
    selected,candidates,missing=train(x,dev,xv,val,args.allow_missing_class)
    source_files=['src/routing/features.py','src/routing/router.py','src/systems/rebuild/shared.py','analysis/train_router_rebuild.py','analysis/devval_inputs.py']
    artifact=dict(selected['artifact'],version='router-rebuild-v2',tau=selected['tau'],C=selected['C'],
        feature_names=list(NAMES),encoder_fingerprint=encoder.fingerprint,missing_classes=missing,
        source_hashes={name:digest(ROOT/name) for name in source_files},seed=42,
        training_source_sha256=digest(paths['development']),validation_source_sha256=digest(paths['validation']),
        training_ids=[q['question_id'] for q in dev],validation_ids=[q['question_id'] for q in val],
        training_repos=sorted({q['repo'] for q in dev}),training_class_counts=dict(Counter(q['gold_route'] for q in dev)),
        validation_class_counts=dict(Counter(q['gold_route'] for q in val)),
        calibration='temperature scaling on leave-one-development-repository-out predictions',
        calibration_folds=selected['folds'],test_inputs=[],human_inputs=[],paraphrase_inputs=[],
        limitation='Absent classes have probability zero; hybrid is reachable through confidence fallback. Validation cannot assess absent classes.' if missing else None)
    path=ROOT/'configs/router_v2.json';save(path,artifact);path.with_suffix('.sha256').write_text(digest(path)+'\n')
    records=[]
    for q,p_row,vector in zip(val,probabilities(xv,artifact),xv):
        records.append(dict(question_id=q['question_id'],repo=q['repo'],question_set=q['question_set'],split='validation',
            category=q['category'],gold_route=q['gold_route'],features=features(q['question'],q['repo']),
            embedding=vector[len(NAMES):].tolist(),probabilities=p_row,**policy(p_row,artifact['tau']),
            router_version='v2',artifact_sha256=digest(path)))
    out=ROOT/'runs/router_v2';write_rows(out/'validation.jsonl',records)
    save(out/'selection.json',[{k:v for k,v in r.items() if k not in {'artifact','folds'}} for r in candidates])
    result=routing_metrics(records);save(out/'validation_metrics.json',result)
    lines=['# Router v2 validation','',f'Development: {len(dev)} T questions. Validation: {len(val)} T questions. P is not used for router training or selection. No test or H questions were read.',
           '',f'Selected C={artifact["C"]}, tau={artifact["tau"]:.2f}, temperature={artifact["temperature"]:.6f}. Validation routing accuracy: {result["accuracy"]:.4%}.',
           '', 'Rows are gold; columns are chosen routes after confidence fallback.', '',
           '| Gold / chosen | graph | vector | hybrid |','|---|---:|---:|---:|']
    lines += ['| '+r+' | '+' | '.join(str(result['confusion_matrix'][r][c]) for c in ROUTES)+' |' for r in ROUTES]
    lines += ['', '| Category | Correct | Count | Accuracy |','|---|---:|---:|---:|']
    lines += [f'| {c} | {v["correct"]} | {v["count"]} | {v["accuracy"]:.4%} |' for c,v in result['per_category'].items()]
    majority=max(result['class_support'].values())/len(val)
    lines += ['',f'Constant-majority validation baseline: {majority:.4%}. Training classes: {artifact["training_class_counts"]}. Validation classes: {artifact["validation_class_counts"]}.',
              '',f'Unsupported training classes: {missing}. No synthetic labels were invented. '+(artifact['limitation'] or ''),
              '', 'Calibration is development-only, using repository-grouped out-of-fold predictions. C and tau are selected on validation; reported validation accuracy is a tuning result, not an unbiased generalization estimate. Template families are disjoint between development and validation, but calibration folds share development families. The vector class has only four training examples.',
              '', 'Router v1 remains available through src.routing.router.RouterV1 and delegates to the unchanged historical rule implementation. Its confidence is heuristic, not calibrated.',
              '', 'The Phase 8 cache-replay sweep is implemented in analysis/routing_evaluation.py; no test sweep was run and no generation API was called.']
    (ROOT/'reports/router_validation.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()

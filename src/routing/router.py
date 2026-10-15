"""Deterministic JSON-weight classifier with development-only calibration."""
import json
from pathlib import Path
import numpy as np
from src.ingest.storage import ROOT,digest
from .features import NAMES,features,matrix

ROUTES=('graph','vector','hybrid')


def policy(probabilities,tau):
    if not 0<=tau<=1:raise ValueError('tau must be in [0,1]')
    if set(probabilities)!=set(ROUTES) or not all(np.isfinite(v) and 0<=v<=1 for v in probabilities.values()):
        raise ValueError('Invalid route probabilities')
    if not np.isclose(sum(probabilities.values()),1):raise ValueError('Probabilities must sum to one')
    preferred=max(ROUTES,key=lambda r:probabilities[r])
    confidence=probabilities[preferred]
    return dict(predicted_route=preferred,confidence=confidence,chosen_route=preferred if confidence>=tau else 'hybrid',tau=tau)


def probabilities(x,artifact):
    z=(np.asarray(x)-np.array(artifact['mean']))/np.array(artifact['scale'])
    logits=z@np.array(artifact['coef']).T+np.array(artifact['intercept'])
    if len(artifact['classes'])==2:logits=np.concatenate([-logits/2,logits/2],axis=1)
    logits/=artifact['temperature'];logits-=logits.max(axis=1,keepdims=True)
    p=np.exp(logits);p/=p.sum(axis=1,keepdims=True)
    return [{route:float(row[artifact['classes'].index(route)]) if route in artifact['classes'] else 0.0 for route in ROUTES} for row in p]


class RouterV2:
    def __init__(self,artifact=None,encoder=None,tau=None):
        self.path=Path(artifact) if artifact else ROOT/'configs/router_v2.json'
        self.artifact=json.loads(self.path.read_text(encoding='utf-8'))
        if self.path.with_suffix('.sha256').read_text().strip()!=digest(self.path):raise ValueError('Router artifact checksum mismatch')
        if self.artifact['feature_names']!=list(NAMES):raise ValueError('Router feature schema mismatch')
        for name,expected in self.artifact['source_hashes'].items():
            if digest(ROOT/name)!=expected:raise ValueError('Router source changed; retrain and version the artifact')
        if encoder is None:
            from src.retrieval.embeddings import Encoder
            encoder=Encoder()
        self.encoder=encoder
        if encoder.fingerprint!=self.artifact['encoder_fingerprint']:raise ValueError('Router encoder fingerprint mismatch')
        self.tau=self.artifact['tau'] if tau is None else tau
        self.cache={}

    def decide(self,question,repo):
        key=(question,repo)
        if key not in self.cache:
            x=matrix([dict(question=question,repo=repo)],self.encoder)
            self.cache[key]=(x,probabilities(x,self.artifact)[0])
        x,p=self.cache[key]
        return dict(features=features(question,repo),embedding=x[0,len(NAMES):].tolist(),
                    probabilities=p,**policy(p,self.tau),router_version='v2',artifact_sha256=digest(self.path))

    def __call__(self,question,repo):return self.decide(question,repo)['chosen_route']


class RouterV1:
    """The unchanged historical rule router, preserved as an explicit ablation."""
    def decide(self,question,repo):
        from src.systems.router import classify,HIGH_CONFIDENCE_THRESHOLD
        result=classify(question)
        return dict(features=features(question,repo),predicted_route=result.preferred_route,
            confidence=result.confidence,chosen_route=result.retrieval_plan,tau=HIGH_CONFIDENCE_THRESHOLD,
            probabilities=None,matched_template=result.matched_template,router_version='v1',
            note='Historical heuristic confidence is not a calibrated probability')
    def __call__(self,question,repo):return self.decide(question,repo)['chosen_route']

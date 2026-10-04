from __future__ import annotations
import json, os
from pathlib import Path
from typing import Any
import faiss
from sentence_transformers import SentenceTransformer
from .common import ROOT, config_get, normalize_text, read_jsonl

CHUNK_SIZE = int(config_get("vector.chunk_size", 1200))
CHUNK_OVERLAP = int(config_get("vector.chunk_overlap", 180))
DEFAULT_TOP_K = int(config_get("vector.top_k", 10))

def chunk_text(text: str) -> list[str]:
    text=normalize_text(text)
    if not text: return []
    if len(text)<=CHUNK_SIZE: return [text]
    out=[]; start=0
    while start<len(text):
        end=min(len(text),start+CHUNK_SIZE); out.append(text[start:end].strip())
        if end>=len(text): break
        start=max(start+1,end-CHUNK_OVERLAP)
    return out

class VectorStore:
    def __init__(self):
        self.dir=ROOT/'data/vector_index'; self.model=SentenceTransformer(os.getenv('EMBEDDING_MODEL','sentence-transformers/all-MiniLM-L6-v2')); self.index=None; self.docs=[]
    def _dirs(self):
        processed=ROOT/'data/processed'; raw=ROOT/'data/raw'; base=processed if processed.exists() and any(processed.iterdir()) else raw
        dirs=[p for p in base.glob('*') if p.is_dir()]; synthetic=ROOT/'data/synthetic'
        if synthetic.exists(): dirs.append(synthetic)
        return list({str(p.resolve()):p for p in dirs}.values())
    def build(self):
        docs=[]
        mapping={'files':'file','commits':'commit','issues':'issue','pulls':'pull_request'}
        for d in self._dirs():
            for filename,kind in mapping.items():
                for r in read_jsonl(d/f'{filename}.jsonl'):
                    aid=str(r.get('id','')).strip()
                    if not aid: continue
                    text='\n'.join([f"Repository: {r.get('repo','')}",f"Path: {r.get('path','')}",f"Number: {r.get('number','')}",f"Title: {r.get('title','')}",f"Author: {r.get('author_email','')}",str(r.get('content','')),str(r.get('message','')),str(r.get('body',''))])
                    for i,chunk in enumerate(chunk_text(text)):
                        docs.append({'id':f'{aid}:chunk:{i}','artifact_id':aid,'repo':r.get('repo'),'kind':kind,'path':r.get('path'),'text':chunk})
        if not docs: raise RuntimeError('No artifacts available for vector indexing')
        emb=self.model.encode([d['text'] for d in docs],normalize_embeddings=True,show_progress_bar=True,batch_size=64).astype('float32')
        idx=faiss.IndexFlatIP(emb.shape[1]); idx.add(emb); self.dir.mkdir(parents=True,exist_ok=True); faiss.write_index(idx,str(self.dir/'index.faiss')); (self.dir/'docs.json').write_text(json.dumps(docs,ensure_ascii=False),encoding='utf-8'); self.index,self.docs=idx,docs
    def load(self):
        self.index=faiss.read_index(str(self.dir/'index.faiss')); self.docs=json.loads((self.dir/'docs.json').read_text(encoding='utf-8'))
    def search(self,q,k=None,*,repository=None,kinds=None):
        if k is None: k=DEFAULT_TOP_K
        if self.index is None: self.load()
        v=self.model.encode([q],normalize_embeddings=True).astype('float32'); candidate=min(max(k*5,k),len(self.docs)); scores,ids=self.index.search(v,candidate); out=[]
        for score,i in zip(scores[0],ids[0]):
            if i<0: continue
            doc=self.docs[i]
            if repository and doc.get('repo')!=repository: continue
            if kinds and doc.get('kind') not in kinds: continue
            out.append({**doc,'score':float(score)})
            if len(out)>=k: break
        return out

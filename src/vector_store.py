from __future__ import annotations
import json, os
from collections import Counter
from src.evaluation.telemetry import CURRENT, retrieval_call
from src.evaluation.reproducibility import sha256
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
        self.dir=Path(os.getenv('VECTOR_INDEX_DIR', str(ROOT/'data/vector_index'))); self.model_name=os.getenv('EMBEDDING_MODEL','sentence-transformers/all-MiniLM-L6-v2'); self.model=SentenceTransformer(self.model_name); self.index=None; self.docs=[]; self.last_search_stats={}
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
        manifest = {
            "schema_version": 2, "embedding_model": self.model_name,
            "chunk_size": CHUNK_SIZE, "chunk_overlap": CHUNK_OVERLAP, "chunk_unit": "characters",
            "doc_count": len(docs), "counts_per_repo": dict(Counter(d["repo"] for d in docs)),
            "counts_per_kind": dict(Counter(d["kind"] for d in docs)),
            "source_dirs": [str(d.resolve()) for d in self._dirs()],
            "synthetic_included": any(d.resolve() == (ROOT/"data/synthetic").resolve() for d in self._dirs()),
            "source_hashes": {str(p.relative_to(ROOT)): sha256(p) for d in self._dirs()
                              for p in d.glob("*.jsonl")},
            "index_sha256": sha256(self.dir/"index.faiss"), "docs_sha256": sha256(self.dir/"docs.json"),
        }
        (self.dir/"manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    def load(self):
        manifest_path = self.dir/"manifest.json"
        if not manifest_path.is_file():
            raise RuntimeError("Vector index manifest missing; rebuild explicitly into results/v2/vector_index. Do not infer legacy provenance.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("embedding_model") != self.model_name:
            raise RuntimeError("Vector index embedding model mismatch")
        for name, field in [("index.faiss", "index_sha256"), ("docs.json", "docs_sha256")]:
            if sha256(self.dir/name) != manifest.get(field):
                raise RuntimeError("Vector index integrity mismatch: " + name)

        self.index=faiss.read_index(str(self.dir/'index.faiss')); self.docs=json.loads((self.dir/'docs.json').read_text(encoding='utf-8'))
        if self.index.ntotal != len(self.docs) or len(self.docs) != manifest["doc_count"]:
            raise RuntimeError("Vector index/document count mismatch")
    @retrieval_call
    def search(self, q, k=None, *, repository=None, kinds=None):
        if k is None:
            k = DEFAULT_TOP_K
        if k <= 0:
            raise ValueError("k must be positive")
        if self.index is None:
            self.load()
        v = self.model.encode([q], normalize_embeddings=True).astype('float32')
        candidate = min(max(k*5, k), len(self.docs))
        total_examined = 0
        rounds = 0
        out = []
        while candidate:
            scores, ids = self.index.search(v, candidate)
            rounds += 1
            total_examined += candidate
            out = []
            for score, i in zip(scores[0], ids[0]):
                if i < 0:
                    continue
                doc = self.docs[i]
                if repository and doc.get('repo') != repository:
                    continue
                if kinds and doc.get('kind') not in kinds:
                    continue
                out.append({**doc, 'score': float(score)})
                if len(out) >= k:
                    break
            if len(out) >= k or candidate == len(self.docs):
                break
            candidate = min(candidate*2, len(self.docs))
        self.last_search_stats = dict(global_candidates_examined=total_examined,
            unique_global_candidates_examined=candidate, search_rounds=rounds,
            repository=repository, returned=len(out), k=k)
        measurement = CURRENT.get()
        if measurement:
            measurement.vector_searches.append(dict(self.last_search_stats))
        return out

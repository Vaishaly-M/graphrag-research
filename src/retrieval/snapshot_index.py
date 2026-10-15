"""Repository-scoped retrieval over the clean FAISS/BM25 corpus."""
import json
import math
from collections import Counter

from src.ingest.storage import digest, read_rows
from .build_indexes import tokens


class SnapshotIndex:
    def __init__(self, directory):
        self.directory=directory
        self.manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
        for name,key in [('chunks.jsonl','chunks_sha256'),('index.faiss','faiss_sha256'),('bm25.json','bm25_sha256')]:
            if digest(directory/name)!=self.manifest[key]:raise ValueError('index integrity mismatch: '+name)
        self.docs=read_rows(directory/'chunks.jsonl')
        self.bm=json.loads((directory/'bm25.json').read_text(encoding='utf-8'))
        self.vector=None;self.model=None

    def bm25(self, question, repo, k=10):
        if k<=0:raise ValueError('k must be positive')
        bm=self.bm
        eligible=[i for i,row in enumerate(self.docs) if row['repo']==repo]
        n=len(eligible)
        if not n:return []
        avg=sum(bm['lengths'][i] for i in eligible)/n;scores=Counter()
        for term in set(tokens(question)):
            hits=[(i,tf) for i,tf in bm['postings'].get(term,[]) if self.docs[i]['repo']==repo]
            idf=math.log(1+(n-len(hits)+0.5)/(len(hits)+0.5))
            for idx,tf in hits:
                norm=tf+bm['k1']*(1-bm['b']+bm['b']*bm['lengths'][idx]/max(avg,1))
                scores[idx]+=idf*tf*(bm['k1']+1)/norm
        return [{**self.docs[i],'score':score} for i,score in scores.most_common(k)]

    def faiss(self, question, repo, k=10):
        import faiss
        from .embeddings import Encoder
        if k<=0:raise ValueError('k must be positive')
        if self.vector is None:
            self.vector=faiss.read_index(str(self.directory/'index.faiss'))
            self.model=Encoder()
            if self.model.fingerprint!=self.manifest['encoder_fingerprint']:
                raise ValueError('Query/index encoder configuration mismatch')
        v=self.model.encode([question],normalize_embeddings=True).astype('float32')
        candidates=min(max(k*5,k),len(self.docs))
        while candidates:
            scores,ids=self.vector.search(v,candidates)
            rows=[{**self.docs[int(i)],'score':float(s)} for s,i in zip(scores[0],ids[0]) if i>=0 and self.docs[int(i)]['repo']==repo]
            if len(rows)>=k or candidates==len(self.docs):return rows[:k]
            candidates=min(candidates*2,len(self.docs))
        return []

"""Dense + lexical reciprocal-rank fusion followed by a real cross-encoder."""
from pathlib import Path
import yaml
from src.ingest.storage import ROOT
from src.retrieval.snapshot_index import SnapshotIndex


class VectorRetriever:
    def __init__(self,directory,config,reranker=None):
        self.store=SnapshotIndex(Path(directory));self.config=config
        if reranker is None:
            import truststore
            truststore.inject_into_ssl()
            import torch
            from sentence_transformers import CrossEncoder
            torch.set_num_threads(2)
            reranker=CrossEncoder(config['reranker'],revision=config['reranker_revision'],device='cpu',max_length=512)
        self.reranker=reranker

    def retrieve(self,question,repo,timing,k=None):
        k=k or self.config['k'];pool=self.config.get('candidate_k',40)
        dense=timing.call('retrieval',lambda:self.store.faiss(question,repo,pool))
        lexical=timing.call('retrieval',lambda:self.store.bm25(question,repo,pool))
        ranks={};docs={}
        for branch in [dense,lexical]:
            for rank,row in enumerate(branch,1):
                ident=row['id'];docs[ident]=row;ranks[ident]=ranks.get(ident,0)+1/(60+rank)
        candidates=[docs[i] for i in sorted(ranks,key=lambda i:(-ranks[i],i))[:pool]]
        if not candidates:return [],['vector:faiss+bm25:repo_filter','vector:empty']
        scores=timing.call('retrieval',lambda:self.reranker.predict([(question,r['text']) for r in candidates],batch_size=16,show_progress_bar=False))
        ordered=sorted(zip(scores,candidates),key=lambda x:(-float(x[0]),x[1]['id']))[:k]
        return [dict(id=r['entity_id'],chunk_id=r['id'],repo=repo,text=r['text'],source='vector',score=float(s)) for s,r in ordered],['vector:faiss+bm25:repo_filter','vector:cross_encoder']

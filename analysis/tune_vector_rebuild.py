"""Full development-repository corpus grid; never reads held-out questions."""
import json
import hashlib
from collections import Counter,defaultdict
from pathlib import Path

import yaml
import numpy as np

from src.ingest.storage import ROOT,read_rows,write_rows,save,digest
from src.retrieval.build_indexes import chunks,tokens
from src.retrieval.embeddings import Encoder
from src.systems.rebuild.vector import VectorRetriever
from src.eval.latency import Timing
from src.eval.metrics import retrieval


def index_variant(size,config,nodes,encoder):
    import faiss
    directory=ROOT/'data/indexes/vector-development'/str(size)
    directory.mkdir(parents=True,exist_ok=True)
    source=ROOT/'data/graph_exports'/config['dataset_id']/'nodes.jsonl'
    docs=list(chunks(nodes,size=size,overlap=round(size*.15)))
    identity=hashlib.sha256((encoder.fingerprint+json.dumps(docs,sort_keys=True)).encode()).hexdigest()
    manifest=directory/'manifest.json'
    if manifest.exists() and json.loads(manifest.read_text())['grid_identity']==identity:return directory
    write_rows(directory/'chunks.jsonl',docs)
    base_dir=ROOT/'data/indexes'/config['dataset_id']
    base_docs=read_rows(base_dir/'chunks.jsonl') if size==1200 else []
    lookup={r['id']:(i,r['text']) for i,r in enumerate(base_docs)}
    base_index=faiss.read_index(str(base_dir/'index.faiss')) if size==1200 else None
    cache=directory/'embeddings';cache.mkdir(exist_ok=True)
    arrays=[]
    for start in range(0,len(docs),1024):
        block=docs[start:start+1024]
        key=hashlib.sha256((identity+str(start)).encode()).hexdigest()[:32]
        path=cache/(key+'.npy')
        if path.exists():arr=np.load(path,allow_pickle=False)
        elif size==1200:
            assert all(lookup[r['id']][1]==r['text'] for r in block)
            arr=np.array([base_index.reconstruct(lookup[r['id']][0]) for r in block])
            np.save(path,arr,allow_pickle=False)
        else:
            arr=encoder.encode([r['text'] for r in block]).astype('float32')
            tmp=path.with_suffix('.tmp')
            with tmp.open('wb') as stream:np.save(stream,arr,allow_pickle=False)
            tmp.replace(path)
        arrays.append(arr);print('Grid index',size,min(start+1024,len(docs)),len(docs),flush=True)
    index=faiss.IndexFlatIP(384);index.add(np.concatenate(arrays));faiss.write_index(index,str(directory/'index.faiss'))
    postings=defaultdict(list);lengths=[]
    for i,row in enumerate(docs):
        words=tokens(row['text']);lengths.append(len(words))
        for token,count in Counter(words).items():postings[token].append([i,count])
    save(directory/'bm25.json',dict(k1=1.5,b=.75,lengths=lengths,postings=postings,chunk_sha256=digest(directory/'chunks.jsonl')))
    save(manifest,dict(grid_identity=identity,encoder_fingerprint=encoder.fingerprint,source_nodes_sha256=digest(source),
        chunks_sha256=digest(directory/'chunks.jsonl'),faiss_sha256=digest(directory/'index.faiss'),bm25_sha256=digest(directory/'bm25.json'),
        chunk_size=size,overlap=round(size*.15),chunk_count=len(docs),by_repo=dict(Counter(r['repo'] for r in docs))))
    return directory


def main():
    import truststore
    truststore.inject_into_ssl()
    from huggingface_hub import HfApi
    split=yaml.safe_load((ROOT/'configs/splits.yaml').read_text())
    questions=read_rows(ROOT/'data/benchmark/template/development.jsonl')
    assert questions and all(q['split']=='development' and q['repo']!='apache/airflow' and q['question_set']=='T' for q in questions)
    nodes=[n for n in read_rows(ROOT/'data/graph_exports'/split['dataset_id']/'nodes.jsonl') if n['repo'] in split['development']['repos']]
    config_path=ROOT/'configs/vector_grid.yaml'
    if config_path.exists():config=yaml.safe_load(config_path.read_text())
    else:
        model='cross-encoder/ms-marco-TinyBERT-L-2-v2'
        config=dict(reranker=model,reranker_revision=HfApi().model_info(model).sha,k=10,candidate_k=40,
                    chunk_sizes=[400,800,1200],overlap_fraction=.15,ks=[5,10,20])
        config_path.write_text(yaml.safe_dump(config),encoding='utf-8')
    encoder=Encoder();results=[];reranker=None
    out=ROOT/'runs/vector_tuning';out.mkdir(parents=True,exist_ok=True)
    for size in [1200,800,400]:
        directory=index_variant(size,split,nodes,encoder)
        vector=VectorRetriever(directory,config,reranker);reranker=vector.reranker
        vector.store.model=encoder
        for k in config['ks']:
            path=out/f'chunk{size}_k{k}.jsonl'
            rows=read_rows(path) if path.exists() else []
            expected_hash=digest(ROOT/'data/benchmark/template/development.jsonl')
            identity=dict(questions_sha256=expected_hash,index_sha256=digest(directory/'manifest.json'),config=config)
            if rows and any(r['identity']!=identity for r in rows):raise ValueError('Stale tuning records')
            done={r['question_id'] for r in rows}
            for q in questions:
                if q['question_id'] in done:continue
                evidence,trace=vector.retrieve(q['question'],q['repo'],Timing(retries=0),k=k)
                ids=list(dict.fromkeys(r['id'] for r in evidence))
                rows.append(dict(question_id=q['question_id'],repo=q['repo'],split='development',identity=identity,
                    evidence_ids=ids,trace=trace,metrics=retrieval(ids,q['gold_evidence_ids'],k=k)))
                write_rows(path,rows)
            recall=sum(r['metrics'][f'evidence_recall@{k}'] for r in rows)/len(rows)
            ndcg=sum(r['metrics']['ndcg@10'] for r in rows)/len(rows)
            results.append(dict(chunk_size=size,overlap=round(size*.15),k=k,questions=len(rows),recall=recall,ndcg=ndcg))
            print('Grid result',results[-1],flush=True)
            report(results,config,complete=False)
        del vector
    best=max(results,key=lambda r:(r['recall'],r['ndcg'],-r['k'],-r['chunk_size']))
    selected=dict(config,**{k:best[k] for k in ['chunk_size','overlap','k']},selection_split='development',selected=True,
                  objective='macro Evidence Recall@k; ties nDCG@10, smaller k, smaller chunk',
                  questions_sha256=expected_hash)
    (ROOT/'configs/vector_selected.yaml').write_text(yaml.safe_dump(selected),encoding='utf-8')
    report(results,config,complete=True)


def report(rows,config,complete):
    lines=['# Vector tuning','',f'Status: {"COMPLETE" if complete else "IN PROGRESS"}. Full four-development-repository corpus; no Airflow or H.',
           '', 'Character chunks; overlap 15%. Dense FAISS + BM25 RRF, then pinned cross-encoder. Retrieval-only selection; no answer-model or test feedback.',
           '', '| Chunk | Overlap | k | Questions | Evidence recall | nDCG@10 |','|---:|---:|---:|---:|---:|---:|']
    lines += [f'| {r["chunk_size"]} | {r["overlap"]} | {r["k"]} | {r["questions"]} | {r["recall"]:.6f} | {r["ndcg"]:.6f} |' for r in rows]
    lines += ['', 'Selection: maximize macro evidence recall; ties nDCG, smaller k, smaller chunk. Canonical repository evidence nodes are not present in the text index and remain in the recall denominator.', '', 'Reranker: '+json.dumps(config,sort_keys=True)]
    (ROOT/'reports/vector_tuning.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':main()

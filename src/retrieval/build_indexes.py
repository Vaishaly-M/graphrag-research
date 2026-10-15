"""FAISS and BM25 share one hashed chunk stream from the canonical graph export."""
import hashlib
import json
import re
from collections import Counter, defaultdict

import yaml

from src.ingest.storage import ROOT, digest, read_rows, save, write_rows


def tokens(text):
    return re.findall(r'[\w]+', text.lower())


def chunks(nodes, size=1200, overlap=180):
    for row in nodes:
        if row['label'] not in {'File','Commit','Issue','PullRequest'}:
            continue
        body = row.get('content') if row['label']=='File' else '\n'.join(str(row.get(k) or '') for k in ['title','body','message','modified_paths'])
        text = f'Repository: {row["repo"]}\nPath: {row.get("path", "")}\nNumber: {row.get("number", "")}\n' + (body or '')
        for start in range(0,len(text),size-overlap):
            part=text[start:start+size]
            yield dict(id=row['id']+f':chunk:{start}', entity_id=row['id'], repo=row['repo'],
                       path=row.get('path'), kind=row['label'], snapshot=row['snapshot'],
                       commit=row.get('sha',row['snapshot']), text=part, start=start)
            if start+size>=len(text):break


def build(config, warm_preview=False, chunk_size=1200, overlap=180, output_directory=None):
    import faiss
    import numpy as np
    from .embeddings import Encoder
    dataset=config['dataset_id'];source=ROOT/'data/graph_exports'/(dataset+'-local-preview' if warm_preview else dataset)/'nodes.jsonl'
    if not warm_preview and json.loads((source.parent/'manifest.json').read_text()).get('incomplete_metadata'):
        raise ValueError('Cannot publish an index from incomplete metadata')
    if not 0<=overlap<chunk_size:raise ValueError('Invalid chunk overlap')
    out=output_directory or ROOT/'data/indexes'/dataset;out.mkdir(parents=True,exist_ok=True)
    order={'File':0,'Commit':1,'Issue':2,'PullRequest':3}
    docs=list(chunks(sorted(read_rows(source),key=lambda r:(order.get(r['label'],9),r['repo'],r['canonical_id'])),size=chunk_size,overlap=overlap))
    docfile=out/'chunks.jsonl'
    if not warm_preview:write_rows(docfile,docs)
    # Immutable source fingerprint prevents reusing checkpoints after any source/config change.
    encoder_config=yaml.safe_load((ROOT/'configs/indexes.yaml').read_text())
    if not (ROOT/encoder_config['onnx_path']).exists():
        import runpy
        runpy.run_path(str(ROOT/'scripts/probe_embedding_backend.py'),run_name='__main__')
    model=Encoder();model_name=model.config['model'];weights=model.fingerprint
    checkpoint=out/'embeddings'/weights[:12]
    checkpoint.mkdir(parents=True,exist_ok=True)
    blocks=[]
    for start in range(0,len(docs),1024):
        blockhash=hashlib.sha256((weights+json.dumps(docs[start:start+1024],sort_keys=True)).encode()).hexdigest()
        # Short filesystem names support Windows MAX_PATH; full hashes are verified.
        path=checkpoint/(blockhash[:32]+'.npy');metadata=path.with_suffix('.json')
        if path.exists() and metadata.exists():
            saved=json.loads(metadata.read_text())
            if saved['key']!=blockhash or saved['sha256']!=digest(path):raise ValueError('embedding checkpoint integrity failure')
            arr=np.load(path,allow_pickle=False)
        else:
            arr=model.encode([r['text'] for r in docs[start:start+1024]],batch_size=64,
                             normalize_embeddings=True,show_progress_bar=False).astype('float32')
            temp=path.with_suffix('.tmp')
            with temp.open('wb') as stream:np.save(stream,arr,allow_pickle=False)
            temp.replace(path)
            save(metadata,dict(key=blockhash,sha256=digest(path)))
        if len(arr)!=len(docs[start:start+1024]):raise ValueError('embedding checkpoint length mismatch')
        blocks.append(arr)
        print('Embedded',min(start+1024,len(docs)),'/',len(docs),flush=True)
    if warm_preview:
        print('Preview embedding cache complete; no final index or manifest published',flush=True)
        return
    chunkhash=digest(docfile)
    vectors=np.concatenate(blocks);index=faiss.IndexFlatIP(vectors.shape[1]);index.add(vectors)
    faiss.write_index(index,str(out/'index.faiss'))
    postings=defaultdict(list);lengths=[]
    for i,row in enumerate(docs):
        terms=tokens(row['text']);lengths.append(len(terms))
        for term,n in Counter(terms).items():postings[term].append([i,n])
    save(out/'bm25.json',dict(k1=1.5,b=0.75,lengths=lengths,postings=dict(postings),chunk_sha256=chunkhash))
    save(out/'manifest.json',dict(dataset=dataset,source_nodes_sha256=digest(source),chunks_sha256=chunkhash,
         faiss_sha256=digest(out/'index.faiss'),bm25_sha256=digest(out/'bm25.json'),
         embedding_model=model_name,encoder_fingerprint=weights,encoder_config=model.config,
         model_artifact_sha256=model.config['onnx_sha256'],chunk_size=chunk_size,overlap=overlap,unit='characters',
         chunk_count=len(docs),by_repo=dict(Counter(r['repo'] for r in docs)),
         nonfile_path_policy='null: commit/issue/PR metadata has no single filesystem path'))
    print('Indexes complete',len(docs),'chunks',flush=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--warm-preview',action='store_true');args=parser.parse_args()
    build(yaml.safe_load((ROOT/'configs/snapshots.yaml').read_text()),args.warm_preview)

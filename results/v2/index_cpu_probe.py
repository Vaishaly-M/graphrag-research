import os,time,json
os.environ['HF_HUB_OFFLINE']='1'
os.environ['OMP_NUM_THREADS']='1'
os.environ['MKL_NUM_THREADS']='1'
import torch
from sentence_transformers import SentenceTransformer
model=SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2',local_files_only=True)
docs=json.load(open('data/vector_index/docs.json',encoding='utf-8'))[8192:8256]
for threads in [8,10]:
    torch.set_num_threads(threads)
    start=time.perf_counter()
    model.encode([d['text'] for d in docs],normalize_embeddings=True,batch_size=64,show_progress_bar=False)
    print(threads,time.perf_counter()-start,flush=True)

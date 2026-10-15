"""Compare FP32 backends on synthetic text only; no benchmark questions used."""
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.data_runtime'))
sys.path.insert(0,str(ROOT))

import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from src.ingest.storage import save, digest


def main():
    import onnxruntime as ort
    torch.set_num_threads(4)
    cache=Path.home()/'.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2/snapshots'
    revision='1110a243fdf4706b3f48f1d95db1a4f5529b4d41'
    name='sentence-transformers/all-MiniLM-L6-v2'
    texts=[f'Repository: synthetic/probe\nPath: src/module_{i}.py\n'+('A component returns its recorded configuration value. '*(1+i*3)) for i in range(16)]
    original=SentenceTransformer(name,revision=revision,local_files_only=True,device='cpu',
                                 model_kwargs={'attn_implementation':'eager'})
    start=time.perf_counter();reference=original.encode(texts,batch_size=16,normalize_embeddings=True)
    torch_s=time.perf_counter()-start
    options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1
    class Export(torch.nn.Module):
        def __init__(self,encoder):super().__init__();self.encoder=encoder
        def forward(self,input_ids,attention_mask,token_type_ids):
            value=self.encoder(dict(input_ids=input_ids,attention_mask=attention_mask,token_type_ids=token_type_ids))['sentence_embedding']
            return torch.nn.functional.normalize(value,p=2,dim=1)
    path=ROOT/'data/models/minilm_fp32.onnx';path.parent.mkdir(parents=True,exist_ok=True)
    example=original.tokenize(texts[:2])
    with torch.no_grad():
        torch.onnx.export(Export(original).eval(),tuple(example[k] for k in ['input_ids','attention_mask','token_type_ids']),str(path),
            input_names=['input_ids','attention_mask','token_type_ids'],output_names=['sentence_embedding'],
            dynamic_axes={k:{0:'batch',1:'sequence'} for k in ['input_ids','attention_mask','token_type_ids']}|{'sentence_embedding':{0:'batch'}},
            opset_version=17,dynamo=False,external_data=False)
    from onnxruntime.transformers.optimizer import optimize_model
    fused=optimize_model(str(path),model_type='bert',num_heads=12,hidden_size=384)
    path=ROOT/'data/models/minilm_fp32_optimized.onnx'
    fused.save_model_to_file(str(path))
    optimized=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])
    names=['input_ids','attention_mask','token_type_ids']
    batch={k:v.numpy() for k,v in original.tokenize(texts).items() if k in names}
    start=time.perf_counter();candidate=optimized.run(None,batch)[0]
    onnx_s=time.perf_counter()-start
    result=dict(model=name,revision=revision,precision='float32',onnx_sha256=digest(path),torch_seconds=torch_s,onnx_seconds=onnx_s,
                max_abs_difference=float(np.max(np.abs(reference-candidate))),
                min_cosine=float(np.min(np.sum(reference*candidate,axis=1))))
    checks=[]
    for sample in [texts[:1],texts[:3],['short', 'Unicode: café λ 日本語', 'x '*500]]:
        expected=original.encode(sample,normalize_embeddings=True)
        actual=optimized.run(None,{k:v.numpy() for k,v in original.tokenize(sample).items() if k in names})[0]
        checks.append(float(np.max(np.abs(expected-actual))))
    result['variable_shape_max_abs_differences']=checks
    result['equivalent']=max([result['max_abs_difference']]+checks)<1e-4 and result['min_cosine']>0.99999
    save(ROOT/'data/indexes/backend_probe.json',result)
    print(json.dumps(result,indent=2),flush=True)
    if not result['equivalent']:raise ValueError('Embedding backend equivalence failed')


if __name__=='__main__':main()

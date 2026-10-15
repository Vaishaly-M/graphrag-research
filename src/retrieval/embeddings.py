"""Pinned FP32 encoder shared by document indexing and query retrieval."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import yaml

from src.ingest.storage import ROOT, digest


class Encoder:
    def __init__(self):
        self.config=yaml.safe_load((ROOT/'configs/indexes.yaml').read_text())
        runtime=ROOT/'.data_runtime_dml'
        if runtime.exists():sys.path.insert(0,str(runtime))
        import onnxruntime as ort
        from transformers import AutoTokenizer
        c=self.config
        path=ROOT/c['onnx_path']
        if digest(path)!=c['onnx_sha256']:raise ValueError('Embedding model artifact hash mismatch')
        self.tokenizer=AutoTokenizer.from_pretrained(c['model'],revision=c['revision'],local_files_only=True)
        options=ort.SessionOptions();options.intra_op_num_threads=c['threads'];options.inter_op_num_threads=1
        options.enable_mem_pattern=False
        options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        if c['provider'] not in ort.get_available_providers():raise RuntimeError('Pinned embedding provider is unavailable')
        self.session=ort.InferenceSession(str(path),sess_options=options,providers=[c['provider'],'CPUExecutionProvider'])
        self.names={v.name for v in self.session.get_inputs()}
        identity=dict(config=c,tokenizer=self.tokenizer.backend_tokenizer.to_str(),
                      implementation_sha256=digest(Path(__file__)),runtime_version=ort.__version__)
        self.fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()

    def encode(self,texts,batch_size=64,**unused):
        # Fixed shapes avoid recompiling the DirectML graph for each sequence length.
        batch_size=self.config['batch_size']
        order=list(range(len(texts)))
        result=np.empty((len(texts),384),dtype='float32')
        for start in range(0,len(order),batch_size):
            indices=order[start:start+batch_size]
            inputs=[texts[i].strip() for i in indices]
            inputs+=['']*(batch_size-len(inputs))
            batch=self.tokenizer(inputs,padding='max_length',truncation=True,
                                 max_length=self.config['max_sequence_length'],return_tensors='np')
            values=self.session.run(None,{k:v.astype('int64',copy=False) for k,v in batch.items() if k in self.names})[0]
            result[indices]=values[:len(indices)]
        return result

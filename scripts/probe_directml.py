"""Optional local-GPU probe on synthetic token IDs; no benchmark questions."""
import json
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.data_runtime_dml'))
import numpy as np
import onnxruntime as ort

options=ort.SessionOptions()
options.intra_op_num_threads=2
options.enable_mem_pattern=False
options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
path=str(ROOT/'data/models/minilm_fp32.onnx')
print('Providers:',ort.get_available_providers(),flush=True)
cpu=ort.InferenceSession(path,sess_options=options,providers=['CPUExecutionProvider'])
gpu=ort.InferenceSession(path,sess_options=options,providers=['DmlExecutionProvider','CPUExecutionProvider'])
results=[]
for batch,length in [(64,256),(64,256),(128,256),(128,256)]:
    ids=np.random.default_rng(42).integers(100,10000,(batch,length),dtype=np.int64)
    mask=np.ones_like(ids);mask[:,-5:]=0
    feed=dict(input_ids=ids,attention_mask=mask,token_type_ids=np.zeros_like(ids))
    start=time.perf_counter();a=cpu.run(None,feed)[0];cpu_s=time.perf_counter()-start
    start=time.perf_counter();b=gpu.run(None,feed)[0];gpu_s=time.perf_counter()-start
    difference=float(np.max(np.abs(a-b)))
    row=dict(batch=batch,length=length,cpu_seconds=cpu_s,gpu_seconds=gpu_s,max_abs_difference=difference)
    print(row,flush=True);results.append(row)
    assert difference<1e-4
(ROOT/'data/indexes/directml_probe.json').write_text(json.dumps(results,indent=2))

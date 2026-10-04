import pandas as pd
from src.common import ROOT, read_jsonl
rows=[]
for p in (ROOT/'results').glob('*_results.jsonl'):
 for r in read_jsonl(p): rows.append({'id':r['id'],'system':r['system'],'question':r['question'],'ground_truth':' | '.join(map(str,r['ground_truth'])),'answer':r.get('answer',''),'incorrect_entity':0,'fabricated_relationship':0,'unsupported_statement':0,'incomplete_answer':0,'annotator_notes':''})
pd.DataFrame(rows).to_csv(ROOT/'results/hallucination_annotation.csv',index=False)

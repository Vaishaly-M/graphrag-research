import argparse,json,re
from src.llm import GeminiClient
from src.systems.base import BaseSystem,add_run_arguments
from src.systems.prompts import ANSWER,ANSWER_MAX_OUTPUT_TOKENS,ANSWER_TEMPERATURE
from src.vector_store import VectorStore
class System(BaseSystem):
 name='vector_rag'
 def __init__(self):self.llm=GeminiClient();self.vector_store=VectorStore()
 def answer(self,question):
  m=re.search(r'\brepository\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)',question,re.I); repo=m.group(1) if m else None; results=self.vector_store.search(question,k=10,repository=repo); answer=self.llm.generate(ANSWER.format(question=question,evidence=json.dumps(results,ensure_ascii=False,default=str)),temperature=ANSWER_TEMPERATURE,max_output_tokens=ANSWER_MAX_OUTPUT_TOKENS).strip(); return {'answer':answer,'selected_retrieval_route':'vector','retrieved_evidence':[str(x.get('artifact_id',x.get('id',x))) if isinstance(x,dict) else str(x) for x in results]}
if __name__=='__main__':
 p=argparse.ArgumentParser();add_run_arguments(p);a=p.parse_args();System().run(benchmark=a.benchmark_file,output_dir=a.output_dir,limit=a.limit,reset=a.reset,repeats=a.repeats)

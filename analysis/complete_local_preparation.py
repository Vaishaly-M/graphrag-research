"""Sequential, resumable local preparation; never runs Gemini or held-out evaluation."""
import subprocess
import sys
import requests
from src.ingest.storage import ROOT,save,now


def main():
    status=ROOT/'runs/local_preparation/status.json'
    stages=['analysis.paraphrase_devval','analysis.tune_vector_rebuild','analysis.publish_selected_vector']
    for module in stages:
        save(status,dict(stage=module,status='running',updated_at=now()))
        try:
            subprocess.run([sys.executable,'-u','-m',module],cwd=ROOT,check=True)
            if module=='analysis.paraphrase_devval':
                requests.post('http://localhost:11434/api/generate',json={'model':'qwen2.5:7b','keep_alive':0},timeout=30).raise_for_status()
        except Exception as exc:
            save(status,dict(stage=module,status='failed',error_type=type(exc).__name__,updated_at=now()))
            raise
    save(status,dict(status='complete',updated_at=now(),live_evaluation='not started'))


if __name__=='__main__':main()

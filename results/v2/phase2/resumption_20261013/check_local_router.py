"""Local transport/schema smoke check; no benchmark answers or scoring."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[4]))
from src.systems.ollama_router_client import OllamaRouterClient
from src.evaluation.telemetry import Measurement,measured
out=Path(__file__).parent
with measured(Measurement(system="phase2_router_smoke",event_path=out/"router_smoke_events.jsonl")):
    raw=OllamaRouterClient().generate('Return ONLY a JSON object with graph, vector, hybrid probabilities summing to one. Choose retrieval for: Which files were changed by a commit?',temperature=0,max_output_tokens=200)
obj=json.loads(raw)
assert set(obj)=={"graph","vector","hybrid"}
assert all(isinstance(x,(float,int)) and x>=0 for x in obj.values()) and abs(sum(obj.values())-1)<=.02
(out/"router_smoke.json").write_text(json.dumps({"status":"PASS","scores":obj,"scope":"local transport/schema only; no benchmark scoring"},indent=2)+"\n")
print("Local router JSON smoke PASS")

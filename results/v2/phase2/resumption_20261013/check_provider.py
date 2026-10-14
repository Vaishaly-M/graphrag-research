"""One non-benchmark request; preserve diagnostic events separately from evaluation."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from src.llm import GeminiClient
from src.evaluation.telemetry import Measurement, measured

directory = Path(__file__).parent / 'provider_recovery'
directory.mkdir(exist_ok=True)
client = GeminiClient()
client.cache_enabled = False
client.request_budget = 1
measurement = Measurement(question_id='provider-health', system='diagnostic', event_path=directory/'events.jsonl')
start = time.perf_counter()
print('Checking configured Gemini model', client.model, flush=True)
try:
    with measured(measurement):
        answer = client.generate('Reply with OK.', temperature=0, max_output_tokens=16)
    result = dict(ok=True, model=client.model, answer=answer, wall_s=time.perf_counter()-start)
except Exception as exc:
    last = measurement.events[-1] if measurement.events else {}
    result = dict(ok=False, model=client.model, error_type=last.get('error') or type(exc).__name__,
                  terminal_exception=type(exc).__name__, provider_status_code=last.get('provider_status_code'),
                  wall_s=time.perf_counter()-start)
(directory/'health.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result), flush=True)
sys.exit(0 if result['ok'] else 1)

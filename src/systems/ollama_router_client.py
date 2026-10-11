"""Local-only LLM router transport; it never substitutes for the generator."""
import json
import time
import urllib.request
from src.evaluation.telemetry import CURRENT, Measurement, utc_now


class OllamaRouterClient:
    def __init__(self, model="qwen2.5:7b", host="http://localhost:11434"):
        self.model, self.host = model, host.rstrip("/")

    def generate(self, prompt, *, temperature=0., max_output_tokens=200):
        m = CURRENT.get() or Measurement(system="llm_router")
        start, started = time.perf_counter(), utc_now()
        failure = None
        m.n_attempts += 1
        try:
            request = urllib.request.Request(self.host+"/api/generate", data=json.dumps(dict(
                model=self.model, prompt=prompt, stream=False, format="json",
                options=dict(temperature=temperature, num_predict=max_output_tokens, seed=20261009))).encode(),
                headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.load(response)
            answer = str(payload.get("response") or "").strip()
            if not answer or not payload.get("done"):
                raise RuntimeError("Empty or incomplete Ollama response")
            return answer
        except Exception as exc:
            failure = type(exc).__name__
            m.llm_failures.append(failure)
            raise
        finally:
            elapsed = time.perf_counter()-start
            m.llm_time_s += elapsed
            m.emit(attempt=1, duration_s=elapsed, start_time=started, end_time=utc_now(),
                status="error" if failure else "ok", error=failure, sleep_s=0., reason="local_router",
                model=self.model, pacing_sleep_s=0., backoff_sleep_s=0., retry_after_s=None)

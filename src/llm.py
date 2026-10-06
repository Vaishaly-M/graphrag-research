"""Gemini client with observable attempts and a content-addressed response cache."""
from __future__ import annotations
import hashlib
import json
import os
import random
import re
import time
import uuid
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from itertools import cycle
from google import genai
from google.genai import types
from .common import ROOT, config_get
from .evaluation.telemetry import CURRENT, Measurement, utc_now


class EmptyModelResponse(RuntimeError):
    pass


class CallBudgetExceeded(RuntimeError):
    pass


def retry_after_seconds(exc):
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) or {}
    value = headers.get("retry-after")
    if value:
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                return max(0.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError):
                pass
    match = re.search(r"retry(?:[_ ]?delay|[_ ]?after)?[\"':= ]+([0-9.]+)s?", str(exc).lower())
    return float(match.group(1)) if match else None


def retryable(exc):
    return any(token in str(exc).lower() for token in (
        "429", "quota", "rate limit", "tempor", "timeout", "connection", "unavailable",
        "resource exhausted", "disconnected", "remoteprotocolerror", "protocol error", "reset by peer", "eof"))


class GeminiClient:
    # Shared budget is used by the latency probe; it counts physical SDK requests, including retries.
    request_budget = None
    requests_used = 0

    def __init__(self, model=None, rpm=None):
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
        keys = self._resolve_keys()
        self._key_cycle = cycle(keys)
        self._clients = {key: genai.Client(api_key=key, http_options=types.HttpOptions(
            timeout=int(os.getenv("LLM_TIMEOUT_MS", "60000")),
            retry_options=types.HttpRetryOptions(attempts=1))) for key in keys}
        self._last_call = {}
        self.interval = 60 / max(1, rpm or int(os.getenv("GEMINI_RPM", str(config_get("llm.default_rpm", 10)))))
        self.cache_enabled = True
        self.cache_dir = ROOT / "results/v2/response_cache"
        self.cache_namespace = "default"
        self.last_cache_hit = False

    @staticmethod
    def _resolve_keys():
        if config_get("llm_key_pool.enabled", False):
            keys = [key.strip() for key in os.getenv("GEMINI_API_KEYS", "").split(",") if key.strip()]
            if keys:
                return keys
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("GEMINI_API_KEY is missing")
        return [key]

    def _cache_path(self, prompt, temperature, max_output_tokens):
        payload = dict(model=self.model, prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                       params=dict(temperature=temperature, max_output_tokens=max_output_tokens))
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return self.cache_dir / self.cache_namespace / (digest + ".json")

    def generate(self, prompt, *, temperature=0.2, max_output_tokens=1024):
        measurement = CURRENT.get() or Measurement()
        self.last_cache_hit = False
        cache = self._cache_path(prompt, temperature, max_output_tokens)
        call_id = uuid.uuid4().hex
        if self.cache_enabled and cache.exists():
            value = json.loads(cache.read_text(encoding="utf-8"))
            answer = str(value["answer"]).strip()
            if not answer:
                measurement.llm_failures.append("EmptyModelResponse: empty cached response")
                raise EmptyModelResponse("Empty cached model response")
            self.last_cache_hit = True
            measurement.n_cache_hits += 1
            measurement.emit(call_id=call_id, attempt=0, duration_s=0.0, status="cache_hit",
                             error=None, sleep_s=0.0, reason="response_cache", start_time=utc_now(),
                             end_time=utc_now(), pacing_sleep_s=0.0, backoff_sleep_s=0.0,
                             retry_after_s=None, model=self.model)
            return answer
        key = next(self._key_cycle)
        client = self._clients[key]
        pacing = max(0.0, self.interval - (time.monotonic() - self._last_call.get(key, 0.0)))
        if pacing:
            start = time.perf_counter()
            time.sleep(pacing)
            pacing = time.perf_counter() - start
            measurement.pacing_sleep_s += pacing
        tries = int(config_get("retry.retries", 6))
        if tries < 1:
            raise ValueError("retry.retries must be positive")
        for attempt in range(1, tries + 1):
            if self.request_budget is not None and GeminiClient.requests_used >= self.request_budget:
                measurement.llm_failures.append("CallBudgetExceeded: physical API request budget exhausted")
                raise CallBudgetExceeded("Physical API request budget exhausted")
            started, start = utc_now(), time.perf_counter()
            GeminiClient.requests_used += 1
            measurement.n_attempts += 1
            error = None
            answer = None
            retry_after = None
            failure = None
            try:
                response = client.models.generate_content(model=self.model, contents=prompt,
                    config=types.GenerateContentConfig(temperature=temperature, max_output_tokens=max_output_tokens))
                self._last_call[key] = time.monotonic()
                answer = (response.text or "").strip()
                if not answer:
                    raise EmptyModelResponse("Model returned empty or whitespace-only text")
            except Exception as exc:
                failure = exc
                # Do not put provider error messages (which may echo credentials/URLs) in the event log.
                error = type(exc).__name__
                retry_after = retry_after_seconds(exc)
            duration = time.perf_counter() - start
            ended = utc_now()
            measurement.llm_time_s += duration
            can_retry = failure is not None and retryable(failure) and attempt < tries
            backoff = 0.0
            if can_retry:
                delay = max(float(config_get("retry.base_delay_s", 1.0)) * 2 ** (attempt - 1), retry_after or 0.0) + random.random()
                start_sleep = time.perf_counter()
                time.sleep(delay)
                backoff = time.perf_counter() - start_sleep
                measurement.backoff_sleep_s += backoff
            measurement.emit(call_id=call_id, attempt=attempt, start_time=started, end_time=ended,
                duration_s=duration, status="error" if failure else "ok", error=error,
                sleep_s=(pacing if attempt == 1 else 0.0) + backoff,
                pacing_sleep_s=pacing if attempt == 1 else 0.0, backoff_sleep_s=backoff,
                retry_after_s=retry_after, reason="retry" if can_retry else "terminal" if failure else "completed",
                model=self.model)
            if failure:
                if can_retry:
                    continue
                measurement.llm_failures.append(error)
                raise failure
            if self.cache_enabled:
                cache.parent.mkdir(parents=True, exist_ok=True)
                temp = cache.with_suffix(".tmp")
                temp.write_text(json.dumps(dict(answer=answer, model=self.model, created_at=utc_now())), encoding="utf-8")
                temp.replace(cache)
            return answer
        raise RuntimeError("Retry loop exhausted without a result")

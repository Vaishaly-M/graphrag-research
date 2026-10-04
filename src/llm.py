from __future__ import annotations
import hashlib
import json
import os
import time
from itertools import cycle
from pathlib import Path
from google import genai
from google.genai import types
from .common import ROOT, config_get, retry


class GeminiClient:
    """
    Gemini API client with pacing, retry, an optional legitimate-key pool,
    and an optional disk cache.

    Key pool: when config/experiment.yaml -> llm_key_pool.enabled is true,
    keys are read from GEMINI_API_KEYS (comma-separated) and calls are
    spread round-robin across them, each individually rate-limited to the
    same RPM as a single key. This only increases throughput proportional
    to the number of keys you legitimately hold; it does not remove or
    evade any single key's own rate limit. It must never be used to rotate
    across separate free-tier accounts to bypass a provider's per-account
    quota. With the pool disabled (the default), behavior is unchanged
    from a single GEMINI_API_KEY.

    Cache: OFF by default. A cache hit skips the real API call, so
    latency_s on that row is not a real measurement -- do not enable this
    for a run whose latency numbers will be reported. See
    config/experiment.yaml -> llm_cache for details.
    """

    def __init__(self, model: str | None = None, rpm: int | None = None):
        self.model = model or os.getenv(
            "GEMINI_MODEL", "gemini-3.1-flash-lite-preview"
        )

        keys = self._resolve_keys()
        self._key_cycle = cycle(keys)
        self._clients = {key: genai.Client(api_key=key) for key in keys}
        self._last_call: dict[str, float] = {}

        default_rpm = config_get("llm.default_rpm", 10)
        self.interval = 60 / max(
            1, rpm or int(os.getenv("GEMINI_RPM", str(default_rpm)))
        )

        self.cache_enabled = bool(config_get("llm_cache.enabled", False))
        self.cache_dir = ROOT / str(
            config_get("llm_cache.directory", ".cache/gemini")
        )
        self.last_cache_hit = False

    @staticmethod
    def _resolve_keys() -> list[str]:
        pool_enabled = bool(config_get("llm_key_pool.enabled", False))

        if pool_enabled:
            raw = os.getenv("GEMINI_API_KEYS", "")
            keys = [key.strip() for key in raw.split(",") if key.strip()]

            if keys:
                return keys

        return [os.environ["GEMINI_API_KEY"]]

    def _cache_path(
        self, prompt: str, temperature: float, max_output_tokens: int
    ) -> Path:
        payload = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.txt"

    def generate(
        self, prompt: str, *, temperature: float = 0.2, max_output_tokens: int = 1024
    ) -> str:
        self.last_cache_hit = False

        if self.cache_enabled:
            cache_path = self._cache_path(prompt, temperature, max_output_tokens)

            if cache_path.exists():
                self.last_cache_hit = True
                return cache_path.read_text(encoding="utf-8")

        key = next(self._key_cycle)
        client = self._clients[key]

        last_call = self._last_call.get(key, 0.0)
        delay = self.interval - (time.monotonic() - last_call)

        if delay > 0:
            time.sleep(delay)

        def call() -> str:
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature, max_output_tokens=max_output_tokens
                ),
            )
            self._last_call[key] = time.monotonic()
            return (response.text or "").strip()

        # Keep the retry policy in experiment.yaml so each measured run
        # records and consistently applies the same resilience settings.
        text = retry(
            call,
            retries=int(config_get("retry.retries", 6)),
            base=float(config_get("retry.base_delay_s", 1.0)),
        )

        if self.cache_enabled:
            cache_path = self._cache_path(prompt, temperature, max_output_tokens)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(text, encoding="utf-8")

        return text

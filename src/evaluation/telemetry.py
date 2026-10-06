"""Per-question instrumentation, independent of retrieval/routing policy."""
from __future__ import annotations

import contextvars
import functools
import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.common import ROOT


def utc_now():
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Measurement:
    question_id: str = "unscoped"
    system: str = "unscoped"
    run_id: int = 1
    attempt_number: int = 1
    event_path: Path = field(default_factory=lambda: ROOT / "logs/llm_events.jsonl")
    retrieval_time_s: float = 0.0
    llm_time_s: float = 0.0
    pacing_sleep_s: float = 0.0
    backoff_sleep_s: float = 0.0
    n_attempts: int = 0
    n_cache_hits: int = 0
    llm_failures: list = field(default_factory=list)
    retrieval_failures: list = field(default_factory=list)
    parse_failures: list = field(default_factory=list)
    events: list = field(default_factory=list)
    vector_searches: list = field(default_factory=list)

    def emit(self, **event):
        record = dict(question_id=self.question_id, system=self.system,
                      run_id=self.run_id, attempt_number=self.attempt_number, **event)
        self.events.append(record)
        self.event_path.parent.mkdir(parents=True, exist_ok=True)
        with self.event_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def timing(self, total):
        wait = self.pacing_sleep_s + self.backoff_sleep_s
        return dict(retrieval_time_s=self.retrieval_time_s, llm_time_s=self.llm_time_s,
                    pacing_sleep_s=self.pacing_sleep_s, backoff_sleep_s=self.backoff_sleep_s,
                    sleep_wait_s=wait, n_attempts=self.n_attempts,
                    n_cache_hits=self.n_cache_hits, total_wall_s=total,
                    latency_s=max(0.0, total - wait),
                    other_time_s=max(0.0, total - wait - self.retrieval_time_s - self.llm_time_s),
                    latency_eligible=self.n_cache_hits == 0 and
                    not any(e.get("status") == "error" for e in self.events))


CURRENT = contextvars.ContextVar("evaluation_measurement", default=None)


@contextmanager
def measured(measurement):
    token = CURRENT.set(measurement)
    try:
        yield measurement
    finally:
        CURRENT.reset(token)


def retrieval_call(function):
    """Time a concrete retrieval API; remember exceptions even if a caller swallows them."""
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        measurement = CURRENT.get()
        start = time.perf_counter()
        try:
            return function(*args, **kwargs)
        except Exception as exc:
            if measurement:
                measurement.retrieval_failures.append(type(exc).__name__ + ": " + str(exc))
            raise
        finally:
            if measurement:
                measurement.retrieval_time_s += time.perf_counter() - start
    return wrapped

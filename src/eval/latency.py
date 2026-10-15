"""Attempt timing with explicit retry events; waits occur between timed attempts."""
import time


class RetryableError(Exception):
    def __init__(self, message, *, status=None, timeout=False):
        super().__init__(message)
        self.status = status
        self.timeout = timeout


class Timing:
    def __init__(self, *, retries=2, backoff=1.0, clock=time.perf_counter,
                 sleep=time.sleep, event_sink=None):
        self.retries, self.backoff = retries, backoff
        self.clock, self.sleep = clock, sleep
        self.event_sink = event_sink or (lambda event: None)
        self.events = []
        self.seconds = {'retrieval': 0.0, 'generation': 0.0}
        self.retry_count = 0
        self.rate_limited = self.timed_out = False
        self.excluded_wait_seconds = 0.0

    def call(self, stage, operation):
        if stage not in self.seconds:
            raise ValueError('Unknown stage')
        for attempt in range(self.retries + 1):
            started = self.clock()
            error = None
            try:
                value = operation()
            except Exception as exc:
                error = exc
            finally:
                elapsed = self.clock() - started
                self.seconds[stage] += elapsed
            if error is None:
                return value
            retryable = isinstance(error, RetryableError)
            self.rate_limited |= retryable and error.status == 429
            self.timed_out |= isinstance(error, TimeoutError) or (retryable and error.timeout)
            retry = (retryable or isinstance(error, TimeoutError)) and attempt < self.retries
            event = dict(stage=stage, attempt=attempt + 1, elapsed_seconds=elapsed,
                         error_type=type(error).__name__, status=getattr(error, 'status', None),
                         timeout=self.timed_out, retry_scheduled=retry)
            # Never log exception strings: provider exceptions may contain credentials.
            self.events.append(event)
            self.event_sink(event)
            if not retry:
                raise error
            self.retry_count += 1
            before = self.clock()
            self.sleep(self.backoff * 2 ** attempt)
            self.excluded_wait_seconds += self.clock() - before

    def result(self, wall_seconds):
        return dict(retrieval_seconds=self.seconds['retrieval'], generation_seconds=self.seconds['generation'],
                    end_to_end_seconds=max(0.0, wall_seconds-self.excluded_wait_seconds),
                    wall_seconds=wall_seconds, excluded_wait_seconds=self.excluded_wait_seconds,
                    retry_count=self.retry_count, rate_limit=self.rate_limited, timeout=self.timed_out,
                    contaminated=bool(self.retry_count or self.rate_limited or self.timed_out))

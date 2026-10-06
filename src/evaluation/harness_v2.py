"""Auditable execution, resumable failures and independent repeat caches."""
from __future__ import annotations
import json
import time
from pathlib import Path
from src.common import ROOT, read_jsonl, write_jsonl
from src.evaluation.metrics_v2 import is_abstention, evaluate_row, summarize
from src.evaluation.reproducibility import save_snapshot, snapshot, source_hashes, write_csv
from src.evaluation.telemetry import Measurement, measured, retrieval_call, utc_now


def measure_answer(system, question_id, question, *, run_id=1, attempt_number=1, event_path=None):
    measurement = Measurement(question_id=str(question_id), system=system.name,
                              run_id=run_id, attempt_number=attempt_number)
    if event_path is not None:
        measurement.event_path = Path(event_path)
    graph = getattr(system, "graph", None)
    original_query = graph.query if graph is not None else None
    if graph is not None:
        graph.query = retrieval_call(original_query)
    started = utc_now()
    start = time.perf_counter()
    result = {}
    error, error_type = None, None
    try:
        with measured(measurement):
            result = system._normalise_result(system.answer(question))
            if not str(result.get("answer") or "").strip():
                raise RuntimeError("Empty system answer")
    except Exception as exc:
        error_type = type(exc).__name__
        error = error_type  # Exception messages can echo credentials/URLs; events retain safe types.
    finally:
        if graph is not None:
            graph.query = original_query
    total = time.perf_counter() - start
    retrieval_errors = list(measurement.retrieval_failures)
    reported = result.get("retrieval_errors") or []
    if isinstance(reported, str):
        try:
            reported = json.loads(reported)
        except ValueError:
            reported = [reported]
    retrieval_errors.extend(reported)
    if retrieval_errors or measurement.llm_failures or measurement.parse_failures:
        error_type = error_type or ("RetrievalError" if retrieval_errors else
                                    "LLMError" if measurement.llm_failures else "ParseError")
        error = error_type
    if error:
        result["answer"] = ""
        result["answer_status"] = "error"
    else:
        result["answer_status"] = "abstained" if is_abstention(result["answer"]) else "answered"
    # Only classify a no-evidence answer as genuine when there was no failed operation.
    result.update(error=error, error_type=error_type,
                  retrieval_error="; ".join(sorted(set(str(x) for x in retrieval_errors))) or None,
                  start_time=started, end_time=utc_now(), vector_searches=measurement.vector_searches,
                  llm_failure_types=measurement.llm_failures, parse_failures=measurement.parse_failures,
                  **measurement.timing(total))
    result["latency_eligible"] = result["latency_eligible"] and not error
    return result, measurement


def run(system, benchmark, output_dir, limit=None, reset=False, repeats=1,
        discard_first_run=False, no_cache=False):
    benchmark = system._resolve_path(benchmark)
    output_dir = system._resolve_path(output_dir).resolve()
    if not output_dir.is_relative_to((ROOT / "results/v2").resolve()):
        raise ValueError("New runs must write under results/v2; old results are read-only")
    if reset:
        raise ValueError("Destructive --reset is disabled; choose a new run name")
    if repeats < 1 or (discard_first_run and repeats < 2):
        raise ValueError("Need positive repeats and at least two when discarding warm-up")
    rows = system._load_benchmark(benchmark)
    ids = [str(r.get("question_id") or r.get("id")) for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate question IDs")
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        rows = rows[:limit]
    save_snapshot(output_dir, snapshot(benchmark, system.name, repeats=repeats,
        discard_first_run=discard_first_run, cache_enabled=not no_cache, limit=limit,
        source_hashes=source_hashes()))
    path = output_dir / f"{system.name}_results.jsonl"
    history = read_jsonl(path)
    llm = getattr(system, "llm", None)
    failures = 0
    for run_id in range(1, repeats+1):
        if llm is not None:
            llm.cache_enabled = not no_cache
            # Within-repeat resumption reuses responses; repeats remain independent model samples.
            llm.cache_dir = output_dir / "response_cache"
            llm.cache_namespace = f"run_{run_id}"
        for row in rows:
            qid = str(row.get("question_id") or row.get("id"))
            key = f"{qid}::run{run_id}"
            previous = [r for r in history if r["run_key"] == key]
            active = [r for r in previous if not r.get("superseded")]
            if active and active[-1].get("answer_status") in {"answered", "abstained"}:
                continue
            attempt_number = max((r.get("attempt_number", 1) for r in previous), default=0)+1
            result, _ = measure_answer(system, qid, row["question"], run_id=run_id,
                                        attempt_number=attempt_number)
            # Only supersede after a replacement attempt has completed. Old attempts are retained.
            for old in active:
                old["superseded"] = True
            record = dict(row, **{})
            record.update(result)
            record.update(question_id=qid, system=system.name, run_id=run_id, run_key=key,
                          attempt_number=attempt_number, superseded=False,
                          warmup=discard_first_run and run_id == 1)
            history.append(record)
            temporary = path.with_suffix(".tmp")
            write_jsonl(temporary, history)
            temporary.replace(path)
            write_csv(path.with_suffix(".csv"), history)
            failures += result["answer_status"] == "error"
            print(f"{key}: {result['answer_status']} wall={result['total_wall_s']:.3f}s attempts={result['n_attempts']}", flush=True)
    scored = [evaluate_row(r) for r in history]
    write_csv(output_dir / "per_question_metrics.csv", scored)
    write_csv(output_dir / "summary_metrics.csv", summarize(scored))
    if failures:
        raise RuntimeError(f"{failures} execution errors recorded; inspect results before resuming")

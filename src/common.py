from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

import yaml
from dotenv import load_dotenv


load_dotenv()

ROOT = Path(__file__).resolve().parents[1]

T = TypeVar("T")

_EXPERIMENT_CONFIG: dict[str, Any] | None = None


def load_experiment_config() -> dict[str, Any]:
    """
    Load config/experiment.yaml once and cache it for the process lifetime.

    Returns an empty dict if the file is missing, so callers can rely on
    config_get() defaults rather than special-casing a missing config file.
    """
    global _EXPERIMENT_CONFIG

    if _EXPERIMENT_CONFIG is None:
        config_path = ROOT / "config" / "experiment.yaml"

        if config_path.exists():
            _EXPERIMENT_CONFIG = yaml.safe_load(
                config_path.read_text(encoding="utf-8")
            ) or {}
        else:
            _EXPERIMENT_CONFIG = {}

    return _EXPERIMENT_CONFIG


def config_get(path: str, default: Any = None) -> Any:
    """
    Fetch a dotted-path value from config/experiment.yaml, e.g. "llm.default_rpm".

    Returns `default` when the file, section, or key is missing.
    """
    node: Any = load_experiment_config()

    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default

        node = node[part]

    return node


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """
    Read a JSONL file.

    Each non-empty line must contain one JSON object.
    """
    file_path = Path(path)

    if not file_path.exists():
        return []

    rows: list[dict[str, Any]] = []

    with file_path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in {file_path} at line "
                    f"{line_number}: {exc}"
                ) from exc

            if not isinstance(value, dict):
                raise ValueError(
                    f"Expected a JSON object in {file_path} at line "
                    f"{line_number}, but received "
                    f"{type(value).__name__}."
                )

            rows.append(value)

    return rows


def append_jsonl(
    path: str | Path,
    row: dict[str, Any],
) -> None:
    """
    Append one dictionary as a JSON line.

    The parent directory is created automatically.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("a", encoding="utf-8") as file:
        json.dump(
            row,
            file,
            ensure_ascii=False,
            default=str,
        )
        file.write("\n")


def ensure_dirs() -> None:
    """Create the standard data/results directory tree if it is missing."""
    for relative in (
        "data/raw",
        "data/processed",
        "data/synthetic",
        "data/benchmark",
        "data/vector_index",
        "data/metadata",
        "results",
        "repos",
    ):
        (ROOT / relative).mkdir(parents=True, exist_ok=True)


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    """
    Write an iterable of dictionaries to a JSONL file, overwriting any
    existing file at that path. The parent directory is created
    automatically.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("w", encoding="utf-8") as file:
        for row in rows:
            json.dump(row, file, ensure_ascii=False, default=str)
            file.write("\n")


def completed_ids(path: str | Path) -> set[str]:
    """
    Return the set of run keys already written to a result JSONL file, for
    resumability.

    `run_key` is preferred when present (multi-repeat runs, WP9): it is
    `question_id` alone for a single-repeat run, or
    `{question_id}::run{N}` for repeat N of a multi-repeat run, so a repeat
    is never mistaken for an already-completed different repeat. Falls
    back to `question_id`/`id` for result files written before `run_key`
    existed.
    """
    completed: set[str] = set()

    for row in read_jsonl(path):
        value = row.get("run_key")

        if value is None:
            value = row.get("question_id")

        if value is None:
            value = row.get("id")

        if value is not None:
            completed.add(str(value))

    return completed


def normalize_text(value: Any) -> str:
    """Convert a value to clean single-line text."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def dedupe_context(items: Iterable[Any]) -> list[Any]:
    """
    Remove duplicate context items while preserving their original order.
    """
    output: list[Any] = []
    seen: set[str] = set()

    for item in items:
        key = json.dumps(
            item,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )

        if key in seen:
            continue

        seen.add(key)
        output.append(item)

    return output


def retry(
    function: Callable[[], T],
    *,
    retries: int = 6,
    base: float = 1.0,
) -> T:
    """
    Retry temporary API or network errors using exponential backoff.
    """
    if retries <= 0:
        raise ValueError("retries must be greater than zero")

    last_exception: Exception | None = None

    for attempt in range(retries):
        try:
            return function()
        except Exception as exc:
            last_exception = exc
            message = str(exc).lower()

            retryable = any(
                text in message
                for text in (
                    "429",
                    "quota",
                    "rate limit",
                    "tempor",
                    "timeout",
                    "connection",
                    "unavailable",
                    "resource exhausted",
                    "service unavailable",
                    "disconnected",
                    "remoteprotocolerror",
                    "protocol error",
                    "reset by peer",
                    "eof",
                )
            )

            if attempt == retries - 1 or not retryable:
                raise

            # Google API errors often include RetryInfo, e.g.
            # ``retryDelay: '52s'``. Honouring it prevents immediately
            # spending another attempt on the same rate limit.
            retry_after = re.search(
                r"retry(?:[_ ]?delay|[_ ]?after)?[\"':= ]+([0-9.]+)s?",
                message,
            )

            delay = base * (2**attempt)
            if retry_after:
                delay = max(delay, float(retry_after.group(1)))

            time.sleep(delay + random.random())

    # This should never be reached, but it satisfies type checking.
    if last_exception is not None:
        raise last_exception

    raise RuntimeError("Retry operation failed unexpectedly.")


def _clean_cypher_for_validation(query: str) -> str:
    """
    Remove comments and string contents before checking Cypher keywords.

    This avoids incorrectly treating keywords inside string literals as
    executable write operations.
    """
    cleaned = re.sub(
        r"/\*.*?\*/",
        " ",
        query,
        flags=re.DOTALL,
    )

    cleaned = re.sub(
        r"//[^\n]*",
        " ",
        cleaned,
    )

    cleaned = re.sub(
        r"'(?:\\.|[^'\\])*'",
        "''",
        cleaned,
    )

    cleaned = re.sub(
        r'"(?:\\.|[^"\\])*"',
        '""',
        cleaned,
    )

    return cleaned


def safe_read_cypher(query: str) -> str:
    """
    Validate and return a read-only Cypher query.

    Write operations and multiple statements are rejected.
    """
    cypher = str(query or "").strip()

    cypher = re.sub(
        r"^```(?:cypher)?\s*",
        "",
        cypher,
        flags=re.IGNORECASE,
    )

    cypher = re.sub(
        r"\s*```$",
        "",
        cypher,
    )

    cypher = re.sub(
        r"^cypher\s*",
        "",
        cypher,
        flags=re.IGNORECASE,
    )

    cypher = cypher.strip().rstrip(";").strip()

    if not cypher:
        raise ValueError("Generated Cypher is empty.")

    cleaned = _clean_cypher_for_validation(cypher)

    if ";" in cleaned:
        raise ValueError(
            "Multiple Cypher statements are not allowed."
        )

    forbidden_pattern = (
        r"\b("
        r"create|"
        r"merge|"
        r"delete|"
        r"detach|"
        r"set|"
        r"remove|"
        r"drop|"
        r"load\s+csv|"
        r"foreach|"
        r"call\s+dbms|"
        r"call\s+apoc\.(?:"
        r"create|merge|delete|periodic"
        r")"
        r")\b"
    )

    if re.search(
        forbidden_pattern,
        cleaned,
        flags=re.IGNORECASE,
    ):
        raise ValueError(
            "Generated Cypher contains a write operation."
        )

    read_pattern = (
        r"\b("
        r"match|"
        r"optional\s+match|"
        r"with|"
        r"unwind|"
        r"return|"
        r"show"
        r")\b"
    )

    if not re.search(
        read_pattern,
        cleaned,
        flags=re.IGNORECASE,
    ):
        raise ValueError(
            "The generated query is not a supported "
            "read-only Cypher query."
        )

    return cypher

"""Immutable run snapshots and small file I/O helpers."""
from __future__ import annotations
import csv
import hashlib
import json
import os
import subprocess
from pathlib import Path
from src.common import ROOT, load_experiment_config


def sha256(path):
    path = Path(path)
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_csv(path, rows, fields=None):
    rows = list(rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                             for k, v in row.items()})


def read_csv(path):
    csv.field_size_limit(100_000_000)
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def snapshot(benchmark, system, **protocol):
    config = load_experiment_config()
    def git(*args):
        return subprocess.check_output(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
                                       cwd=ROOT, stderr=subprocess.DEVNULL, text=True).strip()
    try:
        revision, dirty = git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))
    except subprocess.SubprocessError:
        revision, dirty = None, None
    index = Path(os.getenv("VECTOR_INDEX_DIR", str(ROOT / "data/vector_index")))
    return dict(schema_version=2, git_hash=revision, dirty_tree=dirty, system=system,
                model_name=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview"),
                temperature=config.get("llm", {}).get("temperature_deterministic", 0.0),
                seed=None, seed_note="Gemini generation seed was not set by the existing systems; not changed in Phase 1",
                rpm=int(os.getenv("GEMINI_RPM", str(config.get("llm", {}).get("default_rpm", 10)))),
                retry_settings=config.get("retry", {}), sdk_attempts=1,
                request_timeout_ms=int(os.getenv("LLM_TIMEOUT_MS", "60000")),
                k=config.get("vector", {}).get("top_k", 10),
                chunk_size=config.get("vector", {}).get("chunk_size", 1200),
                chunk_overlap=config.get("vector", {}).get("chunk_overlap", 180),
                embedding_model=os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
                thresholds=config.get("router", {}), index_file_hash=sha256(index / "index.faiss"),
                index_manifest_hash=sha256(index / "manifest.json"), index_directory=str(index),
                benchmark_file=str(Path(benchmark).resolve()), benchmark_sha256=sha256(benchmark),
                config=config, **protocol)


def save_snapshot(directory, value):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "config_snapshot.json"
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        # A dirty flag may change because outputs are written. Actual source hashes are checked.
        comparable = lambda x: {k: v for k, v in x.items() if k != "dirty_tree"}
        if comparable(previous) != comparable(value):
            raise RuntimeError("Run configuration changed; use a new --run-name")
    else:
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def source_hashes():
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted((ROOT / "src").rglob("*.py"))}

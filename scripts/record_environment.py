"""
Record the software/model environment for one experiment run.

Writes results/environment_manifest.json and environment-lock.txt, per the
README's "what you must record for the paper" checklist. Run this once
before every measured pilot or full run, and keep the manifest alongside
that run's result files.

Usage:
    python -m scripts.record_environment
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.common import ROOT


def get_git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


def get_source_fingerprint() -> str:
    """
    Hash every tracked source/config file.

    Used as a substitute for a git commit hash when this project directory
    is not (yet) a git repository. Two runs with the same fingerprint used
    the exact same experiment code.
    """
    hasher = hashlib.sha256()
    paths: list[Path] = []

    for directory in ("src", "config", "scripts"):
        base = ROOT / directory
        if base.exists():
            for pattern in ("*.py", "*.yaml", "*.yml", "*.cypher"):
                paths.extend(base.rglob(pattern))

    for path in sorted(set(paths)):
        hasher.update(str(path.relative_to(ROOT)).replace("\\", "/").encode("utf-8"))
        hasher.update(path.read_bytes())

    return hasher.hexdigest()


def get_pip_freeze() -> list[str]:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"],
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())


def get_neo4j_server_info() -> dict:
    try:
        from src.graph import Graph

        with Graph() as graph:
            rows = graph.query(
                "CALL dbms.components() YIELD name, versions, edition "
                "RETURN name, versions, edition"
            )
        return rows[0] if rows else {"error": "dbms.components() returned no rows"}
    except Exception as error:
        return {"error": f"{type(error).__name__}: {error}"}


def main() -> None:
    load_dotenv(ROOT / ".env")

    git_commit = get_git_commit()

    manifest = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "os": platform.platform(),
        "python_version": sys.version,
        "git_commit": git_commit,
        "source_fingerprint": None if git_commit else get_source_fingerprint(),
        "gemini_model": os.getenv("GEMINI_MODEL"),
        "gemini_rpm": os.getenv("GEMINI_RPM"),
        "embedding_model": os.getenv("EMBEDDING_MODEL"),
        "ollama_model": os.getenv("OLLAMA_MODEL"),
        "neo4j_database": os.getenv("NEO4J_DATABASE"),
        "neo4j_server": get_neo4j_server_info(),
        "pip_freeze": get_pip_freeze(),
    }

    output_path = ROOT / "results" / "environment_manifest.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    lock_path = ROOT / "environment-lock.txt"
    lock_path.write_text("\n".join(manifest["pip_freeze"]) + "\n", encoding="utf-8")

    print(f"Wrote environment manifest to: {output_path}")
    print(f"Wrote package lock to: {lock_path}")

    if git_commit is None:
        print(
            "\nNote: this project directory is not a git repository, so no "
            "commit hash is available. A source_fingerprint hash was "
            "recorded instead so runs can still be compared for code "
            "identity. Consider running 'git init' and committing before "
            "each recorded experiment run for real commit-hash tracking."
        )

    neo4j_info = manifest["neo4j_server"]
    if isinstance(neo4j_info, dict) and "error" in neo4j_info:
        print(f"\nWarning: could not read Neo4j server version: {neo4j_info['error']}")


if __name__ == "__main__":
    main()

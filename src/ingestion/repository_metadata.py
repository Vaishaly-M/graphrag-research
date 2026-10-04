"""
Record per-repository provenance: exact commit SHA, snapshot date, default
branch, and entity counts at each pipeline stage (raw vs. processed).

Run after cloning + mining (data/raw) and, ideally, again after
preprocessing (data/processed) so counts reflect what was actually
collected and what survived cleaning:

    python -m src.ingestion.repository_metadata

Output: one JSON file per repository under data/metadata/<repo>.json, plus
a combined data/metadata/summary.json. This is what "record the run date,
... repository commit SHA" in the README's paper checklist should point to.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.common import ROOT, ensure_dirs, read_jsonl


def run_git(repo_dir: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_dir), *args],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


def git_provenance(repo_dir: Path) -> dict[str, Any]:
    if not repo_dir.exists():
        return {
            "cloned": False,
            "commit_sha": None,
            "commit_date": None,
            "default_branch": None,
        }

    commit_sha = run_git(repo_dir, "rev-parse", "HEAD")
    commit_date = run_git(repo_dir, "log", "-1", "--format=%cI")
    branch = run_git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD")

    if branch in (None, "HEAD"):
        # Shallow clones (--filter=blob:none) commonly leave a detached
        # HEAD. Fall back to the remote's recorded default branch pointer.
        symbolic = run_git(repo_dir, "symbolic-ref", "refs/remotes/origin/HEAD")
        if symbolic:
            branch = symbolic.rsplit("/", 1)[-1]

    return {
        "cloned": True,
        "commit_sha": commit_sha,
        "commit_date": commit_date,
        "default_branch": branch,
    }


def distinct_developer_count(
    commits: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    pulls: list[dict[str, Any]],
) -> int:
    """Count distinct developer identities using the same identity rules
    load_graph.py uses (email > name for commits, GitHub login for
    issues/PRs), so this count is comparable to the graph's Developer node
    count."""
    identities: set[str] = set()

    for commit in commits:
        email = str(commit.get("author_email") or "").strip().lower()
        name = str(commit.get("author_name") or "").strip().lower()

        if email:
            identities.add(f"email:{email}")
        elif name:
            identities.add(f"name:{name}")

    for row in issues + pulls:
        author = row.get("author")
        login = str(author or "").strip().lower()

        if login:
            identities.add(f"github:{login}")

    return len(identities)


def entity_counts(directory: Path) -> dict[str, int] | None:
    if not directory.exists():
        return None

    files = read_jsonl(directory / "files.jsonl")
    commits = read_jsonl(directory / "commits.jsonl")
    issues = read_jsonl(directory / "issues.jsonl")
    pulls = read_jsonl(directory / "pulls.jsonl")

    return {
        "files": len(files),
        "commits": len(commits),
        "issues": len(issues),
        "pull_requests": len(pulls),
        "developers": distinct_developer_count(commits, issues, pulls),
    }


def build_repository_metadata(slug: str) -> dict[str, Any]:
    directory_name = slug.replace("/", "__")

    provenance = git_provenance(ROOT / "repos" / directory_name)
    raw_counts = entity_counts(ROOT / "data" / "raw" / directory_name)
    processed_counts = entity_counts(ROOT / "data" / "processed" / directory_name)

    return {
        "repository": slug,
        "github_url": f"https://github.com/{slug}",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        **provenance,
        "raw_counts": raw_counts,
        "processed_counts": processed_counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record commit SHA, snapshot date, and entity counts per repository."
    )
    parser.add_argument("--config", default="config/repos.yaml")
    args = parser.parse_args()

    ensure_dirs()
    metadata_dir = ROOT / "data" / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    config = yaml.safe_load((ROOT / args.config).read_text(encoding="utf-8"))
    slugs = [item["slug"] for item in config["repositories"]]

    all_metadata: list[dict[str, Any]] = []

    for slug in slugs:
        metadata = build_repository_metadata(slug)
        all_metadata.append(metadata)

        output_path = metadata_dir / f"{slug.replace('/', '__')}.json"
        output_path.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        status = "OK" if metadata["cloned"] else "NOT CLONED"
        print(f"{slug:45s} [{status:11s}] commit={metadata['commit_sha']}")

    summary_path = metadata_dir / "summary.json"
    summary_path.write_text(
        json.dumps({"repositories": all_metadata}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nWrote per-repository metadata to: {metadata_dir}")
    print(f"Wrote combined summary to: {summary_path}")

    uncloned = [m["repository"] for m in all_metadata if not m["cloned"]]
    if uncloned:
        print(
            "\nWarning: the following repositories are not cloned locally, "
            "so no commit SHA could be recorded: " + ", ".join(uncloned)
        )
        print("Run: python -m src.ingestion.clone_repos")


if __name__ == "__main__":
    main()

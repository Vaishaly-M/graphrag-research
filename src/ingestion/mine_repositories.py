
from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from github import Auth, Github
from pydriller import Repository

from src.common import ROOT, ensure_dirs, write_jsonl


TEXT_EXTENSIONS = {
    ".py",
    ".java",
    ".kt",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".cs",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".md",
    ".rst",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".gradle",
    ".properties",
}


def mine_files(repo_dir: Path, slug: str, max_bytes: int) -> list[dict]:
    """Read supported text files from a cloned repository."""

    rows: list[dict] = []

    if not repo_dir.exists():
        print(f"Repository folder not found: {repo_dir}", flush=True)
        return rows

    for path in repo_dir.rglob("*"):
        if not path.is_file():
            continue

        if ".git" in path.parts:
            continue

        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue

        try:
            if path.stat().st_size > max_bytes:
                continue

            text = path.read_text(
                encoding="utf-8",
                errors="ignore",
            )

            if not text.strip():
                continue

            relative_path = path.relative_to(repo_dir).as_posix()

            rows.append(
                {
                    "id": f"{slug}:{relative_path}",
                    "repo": slug,
                    "path": relative_path,
                    "extension": path.suffix.lower(),
                    "content": text,
                }
            )

        except OSError as error:
            print(
                f"Could not read file {path}: {error}",
                flush=True,
            )

    return rows


def mine_commits(
    repo_dir: Path,
    slug: str,
    limit: int,
) -> list[dict]:
    """Mine commit metadata using PyDriller."""

    commits: list[dict] = []

    if not repo_dir.exists():
        raise FileNotFoundError(
            f"Repository folder does not exist: {repo_dir}\n"
            "Run: python -m src.ingestion.clone_repos"
        )

    print(f"Mining commits for {slug}...", flush=True)

    try:
        for index, commit in enumerate(
            Repository(str(repo_dir)).traverse_commits()
        ):
            if index >= limit:
                break

            modified_files = []

            for modified_file in commit.modified_files:
                file_path = modified_file.new_path or modified_file.old_path

                if not file_path:
                    continue

                modified_files.append(
                    {
                        "path": file_path,
                        "added": modified_file.added_lines,
                        "deleted": modified_file.deleted_lines,
                    }
                )

            commits.append(
                {
                    "id": commit.hash,
                    "repo": slug,
                    "message": commit.msg or "",
                    "timestamp": commit.author_date.isoformat(),
                    "author_name": (
                        commit.author.name
                        if commit.author
                        else None
                    ),
                    "author_email": (
                        commit.author.email
                        if commit.author
                        else None
                    ),
                    "modified_files": modified_files,
                }
            )

    except Exception as error:
        raise RuntimeError(
            f"Failed to mine commits for {slug}: {error}"
        ) from error

    return commits


def mine_issues(
    github_client: Github,
    slug: str,
    limit: int,
) -> list[dict]:
    """Download GitHub issues, excluding pull requests."""

    issues: list[dict] = []

    print(f"Downloading issues for {slug}...", flush=True)

    repo = github_client.get_repo(slug)

    for issue in repo.get_issues(
        state="all",
        sort="updated",
        direction="desc",
    ):
        if issue.pull_request is not None:
            continue

        issues.append(
            {
                "id": f"{slug}#issue-{issue.number}",
                "repo": slug,
                "number": issue.number,
                "title": issue.title or "",
                "body": issue.body or "",
                "state": issue.state,
                "author": (
                    issue.user.login
                    if issue.user
                    else None
                ),
                "assignees": [
                    user.login
                    for user in issue.assignees
                ],
                "labels": [
                    label.name
                    for label in issue.labels
                ],
                "created_at": (
                    issue.created_at.isoformat()
                    if issue.created_at
                    else None
                ),
                "updated_at": (
                    issue.updated_at.isoformat()
                    if issue.updated_at
                    else None
                ),
                "closed_at": (
                    issue.closed_at.isoformat()
                    if issue.closed_at
                    else None
                ),
            }
        )

        if len(issues) >= limit:
            break

    return issues


def mine_pull_requests(
    github_client: Github,
    slug: str,
    limit: int,
) -> list[dict]:
    """Download GitHub pull-request metadata."""

    pull_requests: list[dict] = []

    print(f"Downloading pull requests for {slug}...", flush=True)

    repo = github_client.get_repo(slug)

    for pull_request in repo.get_pulls(
        state="all",
        sort="updated",
        direction="desc",
    ):
        pull_requests.append(
            {
                "id": f"{slug}#pr-{pull_request.number}",
                "repo": slug,
                "number": pull_request.number,
                "title": pull_request.title or "",
                "body": pull_request.body or "",
                "state": pull_request.state,
                "author": (
                    pull_request.user.login
                    if pull_request.user
                    else None
                ),
                "merged": bool(pull_request.merged),
                "merge_commit_sha": pull_request.merge_commit_sha,
                "created_at": (
                    pull_request.created_at.isoformat()
                    if pull_request.created_at
                    else None
                ),
                "updated_at": (
                    pull_request.updated_at.isoformat()
                    if pull_request.updated_at
                    else None
                ),
                "closed_at": (
                    pull_request.closed_at.isoformat()
                    if pull_request.closed_at
                    else None
                ),
                "merged_at": (
                    pull_request.merged_at.isoformat()
                    if pull_request.merged_at
                    else None
                ),
            }
        )

        if len(pull_requests) >= limit:
            break

    return pull_requests


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mine commits, issues, pull requests, and files."
    )

    parser.add_argument(
        "--config",
        default="config/repos.yaml",
        help="Path to the repository configuration file.",
    )

    args = parser.parse_args()

    ensure_dirs()

    load_dotenv(ROOT / ".env")

    config_path = ROOT / args.config

    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}"
        )

    with config_path.open(
        "r",
        encoding="utf-8",
    ) as config_file:
        config = yaml.safe_load(config_file)

    if not config:
        raise ValueError(
            f"Configuration file is empty: {config_path}"
        )

    if "repositories" not in config:
        raise KeyError(
            "The configuration must contain a 'repositories' section."
        )

    if "limits" not in config:
        raise KeyError(
            "The configuration must contain a 'limits' section."
        )

    github_token = os.getenv("GITHUB_TOKEN")

    if not github_token:
        raise RuntimeError(
            "GITHUB_TOKEN is missing.\n"
            "Add the following line to your .env file:\n"
            "GITHUB_TOKEN=your_github_token"
        )

    auth = Auth.Token(github_token)
    github_client = Github(auth=auth)

    limits = config["limits"]

    commit_limit = int(
        limits.get("commits_per_repo", 100)
    )
    issue_limit = int(
        limits.get("issues_per_repo", 100)
    )
    pull_limit = int(
        limits.get("pulls_per_repo", 100)
    )
    max_file_bytes = int(
        limits.get("max_file_bytes", 120000)
    )

    for item in config["repositories"]:
        slug = item["slug"]

        local_repo_path = (
            ROOT
            / "repos"
            / slug.replace("/", "__")
        )

        output_directory = (
            ROOT
            / "data"
            / "raw"
            / slug.replace("/", "__")
        )

        print("\n" + "=" * 70, flush=True)
        print(f"Processing repository: {slug}", flush=True)
        print(
            f"Local path: {local_repo_path}",
            flush=True,
        )
        print("=" * 70, flush=True)

        if not local_repo_path.exists():
            print(
                f"Skipping {slug}: cloned repository was not found.",
                flush=True,
            )
            print(
                "Run: python -m src.ingestion.clone_repos",
                flush=True,
            )
            continue

        output_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            commits = mine_commits(
                repo_dir=local_repo_path,
                slug=slug,
                limit=commit_limit,
            )

            issues = mine_issues(
                github_client=github_client,
                slug=slug,
                limit=issue_limit,
            )

            pull_requests = mine_pull_requests(
                github_client=github_client,
                slug=slug,
                limit=pull_limit,
            )

            print(
                f"Reading repository files for {slug}...",
                flush=True,
            )

            files = mine_files(
                repo_dir=local_repo_path,
                slug=slug,
                max_bytes=max_file_bytes,
            )

            write_jsonl(
                output_directory / "commits.jsonl",
                commits,
            )

            write_jsonl(
                output_directory / "issues.jsonl",
                issues,
            )

            write_jsonl(
                output_directory / "pulls.jsonl",
                pull_requests,
            )

            write_jsonl(
                output_directory / "files.jsonl",
                files,
            )

            print(
                f"\nCompleted {slug}",
                flush=True,
            )
            print(
                f"Commits: {len(commits)}",
                flush=True,
            )
            print(
                f"Issues: {len(issues)}",
                flush=True,
            )
            print(
                f"Pull requests: {len(pull_requests)}",
                flush=True,
            )
            print(
                f"Files: {len(files)}",
                flush=True,
            )
            print(
                f"Output: {output_directory}",
                flush=True,
            )

        except Exception as error:
            print(
                f"\nFailed to process {slug}: {error}",
                flush=True,
            )

    github_client.close()


if __name__ == "__main__":
    main()

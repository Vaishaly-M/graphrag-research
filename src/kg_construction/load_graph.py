from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any, Callable, Iterator

from neo4j.exceptions import (
    Neo4jError,
    ServiceUnavailable,
    SessionExpired,
    TransientError,
)

from src.common import ROOT, read_jsonl
from src.graph import Graph


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Source files contain comparatively large text properties.
FILE_BATCH_SIZE = 20

# Commit nodes are loaded separately from modified-file relationships.
COMMIT_BATCH_SIZE = 25

# Each row represents one Commit -> File relationship.
COMMIT_FILE_BATCH_SIZE = 50

ISSUE_BATCH_SIZE = 50
PULL_REQUEST_BATCH_SIZE = 50

# Store only a bounded amount of source text in Neo4j.
# Full content can remain in JSONL and be chunked for vector retrieval later.
MAX_FILE_CONTENT_CHARS = 20_000

# Number of retries for a single row after splitting cannot reduce it further.
MAX_SINGLE_ROW_RETRIES = 3


# ---------------------------------------------------------------------------
# Cypher
# ---------------------------------------------------------------------------

FILE_QUERY = """
UNWIND $rows AS r

MERGE (repo:Repository {id: r.repo})
ON CREATE SET repo.name = r.repo

MERGE (f:File {id: r.id})
SET
    f.repo = r.repo,
    f.path = r.path,
    f.extension = r.extension,
    f.content = r.content,
    f.content_truncated = r.content_truncated,
    f.original_content_length = r.original_content_length

MERGE (repo)-[:CONTAINS_FILE]->(f)
"""


COMMIT_QUERY = """
UNWIND $rows AS r

MERGE (repo:Repository {id: r.repo})
ON CREATE SET repo.name = r.repo

MERGE (c:Commit {id: r.id})
SET
    c.repo = r.repo,
    c.sha = r.sha,
    c.message = r.message,
    c.timestamp = r.timestamp

MERGE (developer:Developer {id: r.author_id})
SET
    developer.name = r.author_name,
    developer.email = r.author_email

MERGE (developer)-[:AUTHORED_COMMIT]->(c)
MERGE (c)-[:COMMITTED_TO]->(repo)
"""


COMMIT_FILE_QUERY = """
UNWIND $rows AS r

MATCH (c:Commit {id: r.commit_id})
MATCH (repo:Repository {id: r.repo})

MERGE (f:File {id: r.file_id})
ON CREATE SET
    f.repo = r.repo,
    f.path = r.path,
    f.extension = r.extension,
    f.content = '',
    f.content_truncated = false,
    f.original_content_length = 0

ON MATCH SET
    f.path = coalesce(f.path, r.path),
    f.extension = coalesce(f.extension, r.extension),
    f.repo = coalesce(f.repo, r.repo)

MERGE (repo)-[:CONTAINS_FILE]->(f)

MERGE (c)-[relationship:MODIFIED_FILE]->(f)
SET
    relationship.added = r.added,
    relationship.deleted = r.deleted,
    relationship.change_type = r.change_type
"""


ISSUE_QUERY = """
UNWIND $rows AS r

MERGE (repo:Repository {id: r.repo})
ON CREATE SET repo.name = r.repo

MERGE (issue:Issue {id: r.id})
SET
    issue.repo = r.repo,
    issue.number = r.number,
    issue.title = r.title,
    issue.body = r.body,
    issue.state = r.state,
    issue.created_at = r.created_at,
    issue.updated_at = r.updated_at,
    issue.closed_at = r.closed_at

MERGE (repo)-[:HAS_ISSUE]->(issue)

FOREACH (
    ignored IN
    CASE
        WHEN r.author_id IS NULL THEN []
        ELSE [1]
    END |

    MERGE (developer:Developer {id: r.author_id})
    SET developer.name = r.author_name
    MERGE (developer)-[:AUTHORED_ISSUE]->(issue)
)

FOREACH (
    assignee IN r.assignees |

    MERGE (developer:Developer {id: assignee.id})
    SET developer.name = assignee.name
    MERGE (issue)-[:ASSIGNED_TO]->(developer)
)
"""


PULL_REQUEST_QUERY = """
UNWIND $rows AS r

MERGE (repo:Repository {id: r.repo})
ON CREATE SET repo.name = r.repo

MERGE (pullRequest:PullRequest {id: r.id})
SET
    pullRequest.repo = r.repo,
    pullRequest.number = r.number,
    pullRequest.title = r.title,
    pullRequest.body = r.body,
    pullRequest.state = r.state,
    pullRequest.merged = r.merged,
    pullRequest.created_at = r.created_at,
    pullRequest.updated_at = r.updated_at,
    pullRequest.closed_at = r.closed_at,
    pullRequest.merged_at = r.merged_at

MERGE (repo)-[:HAS_PR]->(pullRequest)

FOREACH (
    ignored IN
    CASE
        WHEN r.author_id IS NULL THEN []
        ELSE [1]
    END |

    MERGE (developer:Developer {id: r.author_id})
    SET developer.name = r.author_name
    MERGE (developer)-[:AUTHORED_PR]->(pullRequest)
)

FOREACH (
    ignored IN
    CASE
        WHEN r.merge_commit_id IS NULL THEN []
        ELSE [1]
    END |

    MERGE (commit:Commit {id: r.merge_commit_id})
    ON CREATE SET
        commit.repo = r.repo,
        commit.sha = r.merge_commit_sha

    ON MATCH SET
        commit.repo = coalesce(commit.repo, r.repo),
        commit.sha = coalesce(commit.sha, r.merge_commit_sha)

    MERGE (commit)-[:COMMITTED_TO]->(repo)
    MERGE (pullRequest)-[:MERGED_AS]->(commit)
)
"""


# ---------------------------------------------------------------------------
# General helper functions
# ---------------------------------------------------------------------------

def chunks(
    records: list[dict[str, Any]],
    batch_size: int,
) -> Iterator[list[dict[str, Any]]]:
    """Yield fixed-size batches."""

    if batch_size <= 0:
        raise ValueError("Batch size must be greater than zero.")

    for start in range(0, len(records), batch_size):
        yield records[start:start + batch_size]


def clean_text(value: Any) -> str:
    """Convert a nullable value into a stripped string."""

    if value is None:
        return ""

    return str(value).strip()


def normalize_path(value: Any) -> str:
    """Normalize repository paths."""

    return clean_text(value).replace("\\", "/").lstrip("/")


def safe_integer(value: Any) -> int:
    """Convert a value to an integer without stopping the import."""

    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def load_records(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file when it exists."""

    if not path.exists():
        print(f"  Missing {path.name}; skipping it.")
        return []

    records = read_jsonl(path)

    if isinstance(records, list):
        return records

    return list(records)


def is_retryable_neo4j_error(error: Neo4jError) -> bool:
    """
    Identify errors that may be handled by reducing the transaction size.
    """

    code = getattr(error, "code", "") or ""
    message = str(error)

    retryable_markers = (
        "MemoryPoolOutOfMemoryError",
        "dbms.memory.transaction.total.max",
        "TransientError",
        "SessionExpired",
        "ServiceUnavailable",
        "timed out",
        "TimeoutError",
    )

    return (
        any(marker in code for marker in retryable_markers)
        or any(marker in message for marker in retryable_markers)
    )


def execute_batch_with_retry(
    graph: Graph,
    query: str,
    rows: list[dict[str, Any]],
    label: str,
) -> None:
    """
    Import a batch and recursively split it after memory or network errors.

    Splitting continues until successful or until a single invalid row remains.
    """

    if not rows:
        return

    try:
        graph.execute(query, rows=rows)
        return

    except (
        SessionExpired,
        ServiceUnavailable,
        TransientError,
        TimeoutError,
    ) as error:
        retryable_error: Exception = error

    except Neo4jError as error:
        if not is_retryable_neo4j_error(error):
            raise

        retryable_error = error

    print(
        f"\n  Warning: {label} with {len(rows)} rows failed."
    )
    print(f"  Reason: {retryable_error}")

    if len(rows) > 1:
        midpoint = len(rows) // 2

        left_rows = rows[:midpoint]
        right_rows = rows[midpoint:]

        print(
            f"  Splitting into {len(left_rows)} and "
            f"{len(right_rows)} rows."
        )

        execute_batch_with_retry(
            graph=graph,
            query=query,
            rows=left_rows,
            label=f"{label} [left]",
        )

        execute_batch_with_retry(
            graph=graph,
            query=query,
            rows=right_rows,
            label=f"{label} [right]",
        )

        return

    # The batch now contains one row. Retry briefly in case the problem was
    # caused by a temporary Aura connection or memory condition.
    for attempt in range(1, MAX_SINGLE_ROW_RETRIES + 1):
        delay = min(2 ** attempt, 10)

        print(
            f"  Retrying one row in {delay} seconds "
            f"({attempt}/{MAX_SINGLE_ROW_RETRIES})..."
        )

        time.sleep(delay)

        try:
            graph.execute(query, rows=rows)
            return

        except (
            SessionExpired,
            ServiceUnavailable,
            TransientError,
            TimeoutError,
        ) as error:
            retryable_error = error

        except Neo4jError as error:
            if not is_retryable_neo4j_error(error):
                raise

            retryable_error = error

    raise RuntimeError(
        f"Failed to import a single row for {label}. "
        "Inspect the problematic record."
    ) from retryable_error


# ---------------------------------------------------------------------------
# File preparation
# ---------------------------------------------------------------------------

def prepare_file_record(
    record: dict[str, Any],
) -> dict[str, Any] | None:
    repo = clean_text(record.get("repo"))
    file_id = clean_text(record.get("id"))
    path = normalize_path(record.get("path"))

    if not repo or not file_id or not path:
        return None

    raw_content = record.get("content")
    content = "" if raw_content is None else str(raw_content)

    extension = clean_text(record.get("extension"))

    if not extension:
        extension = Path(path).suffix.lower()

    return {
        "repo": repo,
        "id": file_id,
        "path": path,
        "extension": extension,
        "content": content[:MAX_FILE_CONTENT_CHARS],
        "content_truncated": len(content) > MAX_FILE_CONTENT_CHARS,
        "original_content_length": len(content),
    }


# ---------------------------------------------------------------------------
# Commit preparation
# ---------------------------------------------------------------------------

def prepare_modified_file(
    repo: str,
    record: dict[str, Any],
) -> dict[str, Any] | None:
    path = normalize_path(
        record.get("path")
        or record.get("new_path")
        or record.get("old_path")
        or record.get("filename")
    )

    if not path:
        return None

    file_id = clean_text(record.get("file_id"))

    if not file_id:
        file_id = f"{repo}:file:{path}"

    extension = clean_text(record.get("extension"))

    if not extension:
        extension = Path(path).suffix.lower()

    return {
        "file_id": file_id,
        "path": path,
        "extension": extension,
        "added": safe_integer(record.get("added")),
        "deleted": safe_integer(record.get("deleted")),
        "change_type": clean_text(
            record.get("change_type")
            or record.get("type")
        ),
    }


def prepare_commit_record(
    record: dict[str, Any],
) -> dict[str, Any] | None:
    repo = clean_text(record.get("repo"))
    commit_id = clean_text(record.get("id"))

    if not repo or not commit_id:
        return None

    author_email = clean_text(record.get("author_email"))
    author_name = clean_text(record.get("author_name"))

    if author_email:
        author_id = f"email:{author_email.lower()}"
    elif author_name:
        author_id = f"name:{author_name.lower()}"
    else:
        author_id = f"unknown:{commit_id}"

    sha = clean_text(record.get("sha"))

    if not sha and ":commit:" in commit_id:
        sha = commit_id.split(":commit:", 1)[1]

    modified_files: list[dict[str, Any]] = []

    for modified_file in record.get("modified_files") or []:
        if not isinstance(modified_file, dict):
            continue

        prepared_file = prepare_modified_file(
            repo=repo,
            record=modified_file,
        )

        if prepared_file is not None:
            modified_files.append(prepared_file)

    return {
        "repo": repo,
        "id": commit_id,
        "sha": sha,
        "message": clean_text(record.get("message")),
        "timestamp": record.get("timestamp"),
        "author_id": author_id,
        "author_name": author_name,
        "author_email": author_email,
        "modified_files": modified_files,
    }


def flatten_commit_file_relationships(
    commits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Convert nested modified-file lists into individual relationship rows.
    """

    relationships: list[dict[str, Any]] = []

    for commit in commits:
        repo = commit["repo"]
        commit_id = commit["id"]

        for modified_file in commit.get("modified_files", []):
            relationships.append(
                {
                    "repo": repo,
                    "commit_id": commit_id,
                    "file_id": modified_file["file_id"],
                    "path": modified_file["path"],
                    "extension": modified_file["extension"],
                    "added": modified_file["added"],
                    "deleted": modified_file["deleted"],
                    "change_type": modified_file["change_type"],
                }
            )

    return relationships


# ---------------------------------------------------------------------------
# Issue preparation
# ---------------------------------------------------------------------------

def prepare_github_identity(
    value: Any,
) -> tuple[str | None, str]:
    """Create a stable identity from a GitHub user value."""

    if value is None:
        return None, ""

    if isinstance(value, dict):
        raw_id = clean_text(
            value.get("id")
            or value.get("login")
            or value.get("username")
            or value.get("name")
        )

        name = clean_text(
            value.get("name")
            or value.get("login")
            or value.get("username")
        )
    else:
        raw_id = clean_text(value)
        name = raw_id

    if not raw_id:
        return None, name

    return f"github:{raw_id.lower()}", name


def prepare_issue_record(
    record: dict[str, Any],
) -> dict[str, Any] | None:
    repo = clean_text(record.get("repo"))
    issue_id = clean_text(record.get("id"))

    if not repo or not issue_id:
        return None

    author_id, author_name = prepare_github_identity(
        record.get("author")
    )

    assignees: list[dict[str, str]] = []

    for raw_assignee in record.get("assignees") or []:
        assignee_id, assignee_name = prepare_github_identity(
            raw_assignee
        )

        if assignee_id:
            assignees.append(
                {
                    "id": assignee_id,
                    "name": assignee_name,
                }
            )

    return {
        "repo": repo,
        "id": issue_id,
        "number": record.get("number"),
        "title": clean_text(record.get("title")),
        "body": clean_text(record.get("body")),
        "state": clean_text(record.get("state")),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "closed_at": record.get("closed_at"),
        "author_id": author_id,
        "author_name": author_name,
        "assignees": assignees,
    }


# ---------------------------------------------------------------------------
# Pull-request preparation
# ---------------------------------------------------------------------------

def prepare_pull_request_record(
    record: dict[str, Any],
) -> dict[str, Any] | None:
    repo = clean_text(record.get("repo"))
    pull_request_id = clean_text(record.get("id"))

    if not repo or not pull_request_id:
        return None

    author_id, author_name = prepare_github_identity(
        record.get("author")
    )

    merge_commit_sha = clean_text(
        record.get("merge_commit_sha")
    )

    merge_commit_id = (
        f"{repo}:commit:{merge_commit_sha}"
        if merge_commit_sha
        else None
    )

    return {
        "repo": repo,
        "id": pull_request_id,
        "number": record.get("number"),
        "title": clean_text(record.get("title")),
        "body": clean_text(record.get("body")),
        "state": clean_text(record.get("state")),
        "merged": bool(record.get("merged", False)),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "closed_at": record.get("closed_at"),
        "merged_at": record.get("merged_at"),
        "author_id": author_id,
        "author_name": author_name,
        "merge_commit_sha": merge_commit_sha or None,
        "merge_commit_id": merge_commit_id,
    }


# ---------------------------------------------------------------------------
# Generic preparation and import functions
# ---------------------------------------------------------------------------

PreparationFunction = Callable[
    [dict[str, Any]],
    dict[str, Any] | None,
]


def prepare_records(
    records: list[dict[str, Any]],
    preparation_function: PreparationFunction,
) -> tuple[list[dict[str, Any]], int]:
    prepared: list[dict[str, Any]] = []
    skipped = 0

    for record in records:
        prepared_record = preparation_function(record)

        if prepared_record is None:
            skipped += 1
        else:
            prepared.append(prepared_record)

    return prepared, skipped


def import_dataset(
    graph: Graph,
    records: list[dict[str, Any]],
    query: str,
    batch_size: int,
    label: str,
) -> None:
    total = len(records)

    if total == 0:
        print(f"  {label}: no records found.")
        return

    completed = 0

    for batch_number, batch in enumerate(
        chunks(records, batch_size),
        start=1,
    ):
        execute_batch_with_retry(
            graph=graph,
            query=query,
            rows=batch,
            label=f"{label} batch {batch_number}",
        )

        completed += len(batch)

        print(
            f"\r  {label}: {completed}/{total} imported",
            end="",
            flush=True,
        )

    print()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def apply_schema(graph: Graph) -> None:
    schema_path = (
        ROOT
        / "src"
        / "kg_construction"
        / "schema.cypher"
    )

    if not schema_path.exists():
        raise FileNotFoundError(
            f"Schema file not found: {schema_path}"
        )

    schema_text = schema_path.read_text(encoding="utf-8")

    statements = [
        statement.strip()
        for statement in schema_text.split(";")
        if statement.strip()
    ]

    print(f"Applying {len(statements)} schema statements...")

    for index, statement in enumerate(statements, start=1):
        graph.execute(statement)

        print(
            f"  Schema statement "
            f"{index}/{len(statements)} applied."
        )


# ---------------------------------------------------------------------------
# Input directories
# ---------------------------------------------------------------------------

def find_input_directories(
    source: str,
    include_synthetic: bool,
) -> list[Path]:
    base = ROOT / "data" / source

    if not base.exists():
        raise FileNotFoundError(
            f"Input directory does not exist: {base}"
        )

    directories = sorted(
        path
        for path in base.iterdir()
        if path.is_dir()
    )

    if source == "raw" and include_synthetic:
        synthetic_directory = ROOT / "data" / "synthetic"

        if synthetic_directory.exists():
            directories.append(synthetic_directory)
        else:
            print(
                "Warning: data/synthetic does not exist."
            )

    # Remove duplicate directory entries.
    unique_directories: dict[str, Path] = {}

    for directory in directories:
        unique_directories[str(directory.resolve())] = directory

    result = list(unique_directories.values())

    if not result:
        raise FileNotFoundError(
            f"No repository directories found in {base}. "
            "Run preprocessing first."
        )

    return result


# ---------------------------------------------------------------------------
# Repository import
# ---------------------------------------------------------------------------

def import_repository(
    graph: Graph,
    directory: Path,
) -> None:
    print(
        f"\nImporting repository directory: "
        f"{directory.name}"
    )

    raw_files = load_records(
        directory / "files.jsonl"
    )

    raw_commits = load_records(
        directory / "commits.jsonl"
    )

    raw_issues = load_records(
        directory / "issues.jsonl"
    )

    raw_pull_requests = load_records(
        directory / "pulls.jsonl"
    )

    files, skipped_files = prepare_records(
        raw_files,
        prepare_file_record,
    )

    commits, skipped_commits = prepare_records(
        raw_commits,
        prepare_commit_record,
    )

    issues, skipped_issues = prepare_records(
        raw_issues,
        prepare_issue_record,
    )

    pull_requests, skipped_pull_requests = prepare_records(
        raw_pull_requests,
        prepare_pull_request_record,
    )

    commit_file_relationships = (
        flatten_commit_file_relationships(commits)
    )

    print(
        "  Prepared records: "
        f"{len(files)} files, "
        f"{len(commits)} commits, "
        f"{len(issues)} issues, "
        f"{len(pull_requests)} pull requests."
    )

    print(
        "  Prepared commit-file relationships: "
        f"{len(commit_file_relationships)}"
    )

    total_skipped = (
        skipped_files
        + skipped_commits
        + skipped_issues
        + skipped_pull_requests
    )

    if total_skipped:
        print(
            "  Skipped invalid records: "
            f"{skipped_files} files, "
            f"{skipped_commits} commits, "
            f"{skipped_issues} issues, "
            f"{skipped_pull_requests} pull requests."
        )

    # Load file nodes first.
    import_dataset(
        graph=graph,
        records=files,
        query=FILE_QUERY,
        batch_size=FILE_BATCH_SIZE,
        label="Files",
    )

    # Load commit nodes without nested modified-file arrays.
    import_dataset(
        graph=graph,
        records=commits,
        query=COMMIT_QUERY,
        batch_size=COMMIT_BATCH_SIZE,
        label="Commits",
    )

    # Load flattened relationships separately.
    import_dataset(
        graph=graph,
        records=commit_file_relationships,
        query=COMMIT_FILE_QUERY,
        batch_size=COMMIT_FILE_BATCH_SIZE,
        label="Commit-file relationships",
    )

    import_dataset(
        graph=graph,
        records=issues,
        query=ISSUE_QUERY,
        batch_size=ISSUE_BATCH_SIZE,
        label="Issues",
    )

    import_dataset(
        graph=graph,
        records=pull_requests,
        query=PULL_REQUEST_QUERY,
        batch_size=PULL_REQUEST_BATCH_SIZE,
        label="Pull requests",
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_graph_summary(graph: Graph) -> None:
    print("\nKnowledge graph node summary:")

    node_counts = graph.query(
        """
        MATCH (node)
        UNWIND labels(node) AS label
        RETURN label, count(*) AS count
        ORDER BY count DESC, label
        """
    )

    for row in node_counts:
        print(
            f"  {row['label']}: {row['count']}"
        )

    print("\nKnowledge graph relationship summary:")

    relationship_counts = graph.query(
        """
        MATCH ()-[relationship]->()
        RETURN
            type(relationship) AS relationship_type,
            count(*) AS count
        ORDER BY count DESC, relationship_type
        """
    )

    for row in relationship_counts:
        print(
            f"  {row['relationship_type']}: "
            f"{row['count']}"
        )


# ---------------------------------------------------------------------------
# Command-line arguments
# ---------------------------------------------------------------------------

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Load processed repository data into Neo4j."
        )
    )

    parser.add_argument(
        "--source",
        choices=["processed", "raw"],
        default="processed",
        help=(
            "Use processed data for the experiment. "
            "Raw data should only be used for debugging."
        ),
    )

    parser.add_argument(
        "--include-synthetic",
        action="store_true",
        help=(
            "Include data/synthetic only when "
            "--source raw is selected."
        ),
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    arguments = parse_arguments()

    print("Connecting to Neo4j...")

    graph = Graph()

    try:
        apply_schema(graph)

        directories = find_input_directories(
            source=arguments.source,
            include_synthetic=arguments.include_synthetic,
        )

        print(
            f"\nFound {len(directories)} repository "
            f"directories under data/{arguments.source}."
        )

        for directory in directories:
            import_repository(
                graph=graph,
                directory=directory,
            )

        print_graph_summary(graph)

        print(
            "\nKnowledge graph loading completed successfully."
        )

    finally:
        graph.close()


if __name__ == "__main__":
    main()
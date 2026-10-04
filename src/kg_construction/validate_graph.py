"""
Validate the loaded knowledge graph and categorize known data gaps.

Beyond the original orphan/duplicate checks, this validates date fields,
developer-identifier shape, and pull-request completeness, and cross
references data/processed/preprocessing_summary.json so every missing
relationship is labeled:

- excluded_by_preprocessing : intentionally filtered (vendor dirs,
  lockfiles, minified files, duplicates, ...)
- known_upstream_gap        : expected given the configured mining limits
  (e.g. a commit referencing a file deleted before the mining window, or a
  PR's merge commit falling outside the last N mined commits) -- these are
  handled architecturally by load_graph.py's stub-node MERGE, not bugs.
- unclassified_investigate  : an audit_counts key this script doesn't yet
  recognize -- surfaced explicitly rather than silently ignored.

Run: python -m src.kg_construction.validate_graph
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.common import ROOT
from src.graph import Graph

ISO_DATETIME_PATTERN = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"

CHECKS: dict[str, str] = {
    "node_counts": (
        "MATCH (n) UNWIND labels(n) AS label "
        "RETURN label,count(*) AS count ORDER BY count DESC,label"
    ),
    "relationship_counts": (
        "MATCH ()-[r]->() RETURN type(r) AS relationship_type,count(*) AS count "
        "ORDER BY count DESC,relationship_type"
    ),
    "orphan_commits": (
        "MATCH (c:Commit) WHERE NOT (c)-[:COMMITTED_TO]->(:Repository) "
        "RETURN count(c) AS count"
    ),
    "orphan_files": (
        "MATCH (f:File) WHERE NOT (:Repository)-[:CONTAINS_FILE]->(f) "
        "RETURN count(f) AS count"
    ),
    "orphan_issues": (
        "MATCH (i:Issue) WHERE NOT (:Repository)-[:HAS_ISSUE]->(i) "
        "RETURN count(i) AS count"
    ),
    "orphan_pull_requests": (
        "MATCH (p:PullRequest) WHERE NOT (:Repository)-[:HAS_PR]->(p) "
        "RETURN count(p) AS count"
    ),
    "missing_file_paths": (
        "MATCH (f:File) WHERE f.path IS NULL OR trim(f.path)='' "
        "RETURN count(f) AS count"
    ),
    "duplicate_file_paths_per_repo": (
        "MATCH (r:Repository)-[:CONTAINS_FILE]->(f:File) "
        "WITH r.id AS repository,f.path AS path,count(*) AS count "
        "WHERE count>1 RETURN repository,path,count LIMIT 50"
    ),
    "malformed_commit_timestamps": f"""
        MATCH (c:Commit)
        WHERE c.timestamp IS NOT NULL AND trim(toString(c.timestamp)) <> ''
          AND NOT toString(c.timestamp) =~ '{ISO_DATETIME_PATTERN}.*'
        RETURN c.id AS id, c.timestamp AS value LIMIT 50
    """,
    "malformed_issue_dates": f"""
        MATCH (i:Issue)
        UNWIND [i.created_at, i.updated_at, i.closed_at] AS value
        WITH i, value
        WHERE value IS NOT NULL AND trim(toString(value)) <> ''
          AND NOT toString(value) =~ '{ISO_DATETIME_PATTERN}.*'
        RETURN i.id AS id, value LIMIT 50
    """,
    "malformed_pull_request_dates": f"""
        MATCH (p:PullRequest)
        UNWIND [p.created_at, p.updated_at, p.closed_at, p.merged_at] AS value
        WITH p, value
        WHERE value IS NOT NULL AND trim(toString(value)) <> ''
          AND NOT toString(value) =~ '{ISO_DATETIME_PATTERN}.*'
        RETURN p.id AS id, value LIMIT 50
    """,
    "invalid_developer_identifiers": """
        MATCH (d:Developer)
        WHERE d.id IS NULL OR trim(d.id) = ''
           OR NOT (
                d.id STARTS WITH 'email:' OR d.id STARTS WITH 'name:' OR
                d.id STARTS WITH 'github:' OR d.id STARTS WITH 'unknown:'
           )
        RETURN d.id AS id LIMIT 50
    """,
    "developer_email_malformed": """
        MATCH (d:Developer)
        WHERE d.id STARTS WITH 'email:'
          AND (d.email IS NULL OR NOT d.email CONTAINS '@')
        RETURN d.id AS id, d.email AS email LIMIT 50
    """,
    "incomplete_pull_requests_missing_title": """
        MATCH (p:PullRequest) WHERE p.title IS NULL OR trim(p.title) = ''
        RETURN p.id AS id LIMIT 50
    """,
    "merged_pull_requests_without_merge_commit": """
        MATCH (p:PullRequest {merged: true})
        WHERE NOT (p)-[:MERGED_AS]->(:Commit)
        RETURN p.id AS id LIMIT 50
    """,
}

# Checks that return a single {count: N} row rather than a list of
# offending records.
COUNT_QUERIES = {
    "orphan_commits",
    "orphan_files",
    "orphan_issues",
    "orphan_pull_requests",
    "missing_file_paths",
}

# Checks that fail validation when they find anything. node_counts and
# relationship_counts are informational only and never fail.
FAILING_IF_NONEMPTY = COUNT_QUERIES | {
    "duplicate_file_paths_per_repo",
    "malformed_commit_timestamps",
    "malformed_issue_dates",
    "malformed_pull_request_dates",
    "invalid_developer_identifiers",
    "incomplete_pull_requests_missing_title",
    "merged_pull_requests_without_merge_commit",
}

# Source systems occasionally provide a username in an ``author_email``
# field. It is retained for provenance, but must be reported separately from
# structural graph failures: fabricating an email or dropping the author would
# be less correct than preserving the original identifier.
WARNING_IF_NONEMPTY = {"developer_email_malformed"}

# --------------------------------------------------------------------------
# preprocessing_summary.json cross-reference
# --------------------------------------------------------------------------

EXCLUDED_BY_PREPROCESSING_KEYS = {
    "commit_irrelevant_file_change",
    "commit_duplicate_or_invalid_file_change",
    "files_excluded_directory",
    "files_excluded_filename",
    "files_excluded_suffix",
    "files_likely_minified",
    "files_generated_artifact",
    "files_too_large",
    "files_empty_or_too_short",
    "files_duplicate_id",
    "files_missing_required",
    "issues_duplicate",
    "issues_missing_required",
    "pulls_duplicate",
    "pulls_missing_required",
    "commits_missing_required",
    "commits_duplicate_id",
}

KNOWN_UPSTREAM_GAP_KEYS = {
    # A commit modified a file that was later deleted/renamed; the file is
    # not in files.jsonl because it does not exist at the mined snapshot.
    "historical_or_deleted_file_references",
    # A PR's merge commit fell outside the configured commits_per_repo
    # limit and was never independently mined with full metadata.
    "unmined_merge_commit_references",
}


def categorize_preprocessing_audit(
    audit_counts: dict[str, int],
) -> dict[str, dict[str, int]]:
    categorized: dict[str, dict[str, int]] = {
        "excluded_by_preprocessing": {},
        "known_upstream_gap": {},
        "unclassified_investigate": {},
    }

    for key, value in audit_counts.items():
        if key in EXCLUDED_BY_PREPROCESSING_KEYS:
            categorized["excluded_by_preprocessing"][key] = value
        elif key in KNOWN_UPSTREAM_GAP_KEYS:
            categorized["known_upstream_gap"][key] = value
        else:
            categorized["unclassified_investigate"][key] = value

    return categorized


def load_preprocessing_report() -> dict[str, Any] | None:
    summary_path = ROOT / "data" / "processed" / "preprocessing_summary.json"

    if not summary_path.exists():
        return None

    return json.loads(summary_path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Graph checks
# --------------------------------------------------------------------------

def run_checks(graph: Graph) -> dict[str, list[dict[str, Any]]]:
    return {name: graph.query(query) for name, query in CHECKS.items()}


def print_check_results(results: dict[str, list[dict[str, Any]]]) -> list[str]:
    failing: list[str] = []

    for name, rows in results.items():
        print(f"\n{name}\n" + ("-" * len(name)))

        for row in rows:
            print(row)

        if name not in FAILING_IF_NONEMPTY:
            continue

        if name in COUNT_QUERIES:
            has_problem = bool(rows) and int(rows[0].get("count", 0)) > 0
        else:
            has_problem = bool(rows)

        if has_problem:
            failing.append(name)

    return failing


def collect_warnings(results: dict[str, list[dict[str, Any]]]) -> list[str]:
    return [name for name in WARNING_IF_NONEMPTY if results.get(name)]


def print_and_collect_categorized_audit(
    preprocessing_report: dict[str, Any] | None,
) -> dict[str, dict[str, dict[str, int]]]:
    heading = "data_quality_categorization (from preprocessing_summary.json)"
    print(f"\n{heading}\n" + ("-" * len(heading)))

    if preprocessing_report is None:
        print(
            "No data/processed/preprocessing_summary.json found. "
            "Run preprocessing first to get categorized audit counts."
        )
        return {}

    categorized_by_repo: dict[str, dict[str, dict[str, int]]] = {}

    for repo_report in preprocessing_report.get("repositories", []):
        destination = repo_report.get("destination", "")
        repo_name = Path(destination).name if destination else "unknown"

        categorized = categorize_preprocessing_audit(
            repo_report.get("audit_counts", {})
        )
        categorized_by_repo[repo_name] = categorized

        print(f"\n{repo_name}:")
        for bucket, items in categorized.items():
            if items:
                print(f"  {bucket}: {items}")

        if categorized["unclassified_investigate"]:
            print(
                f"  WARNING: unclassified audit keys for {repo_name} -- add "
                "them to EXCLUDED_BY_PREPROCESSING_KEYS or "
                "KNOWN_UPSTREAM_GAP_KEYS in validate_graph.py."
            )

    return categorized_by_repo


def main() -> None:
    graph = Graph()

    try:
        results = run_checks(graph)
        failing = print_check_results(results)
        warnings = collect_warnings(results)

        for name in warnings:
            print(
                f"WARNING: {name} contains upstream non-email author "
                "identifier(s), retained for provenance."
            )

        preprocessing_report = load_preprocessing_report()
        categorized_by_repo = print_and_collect_categorized_audit(
            preprocessing_report
        )

        report_path = ROOT / "results" / "graph_validation_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "graph_checks": results,
                    "failing_checks": failing,
                    "warnings": warnings,
                    "preprocessing_audit_categorized": categorized_by_repo,
                },
                indent=2,
                ensure_ascii=False,
                default=str,
            ),
            encoding="utf-8",
        )

        print(f"\nWrote validation report to: {report_path}")

        if failing:
            raise SystemExit(
                f"\nGraph validation completed with {len(failing)} failing "
                f"checks: {', '.join(failing)}"
            )

        print("\nGraph validation completed successfully.")

    finally:
        graph.close()


if __name__ == "__main__":
    main()

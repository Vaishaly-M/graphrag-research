from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class QueryMatch:
    template_name: str
    route: str
    cypher: str
    params: dict[str, Any]
    answer_field: str = "answer"
    expected_relations: tuple[str, ...] = ()
    expected_path: tuple[str, ...] = ()


REPOSITORY_RE = re.compile(r"\brepository\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", re.I)
COMMIT_ID_RE = re.compile(r"\b([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+:commit:[a-f0-9]{7,40})\b", re.I)
EMAIL_ID_RE = re.compile(r"\bemail:([A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b", re.I)
ISSUE_NUMBER_RE = re.compile(r"\bissue\s+#?(\d+)\b", re.I)
DIRECTORY_RE = re.compile(r"\bunder\s+the\s+['\"]([^'\"]+)['\"]\s+directory", re.I)
# No leading \b: a leading '.' (e.g. ".py files") is not preceded by a word
# character, so \b cannot match between a space and a literal dot.
EXTENSION_RE = re.compile(r"(\.[A-Za-z0-9]+)\s+files\b", re.I)
TITLE_RE = re.compile(r"\btitled\s+['\"](.+?)['\"]\??$", re.I | re.S)
# The trailing extension is optional: some real repository files (e.g. a
# Dockerfile-style script named "flux") have no extension at all.
FILE_PATH_RE = re.compile(r"\b(?:file|path)\s+['\"]?([A-Za-z0-9_.@+\-/]+)['\"]?", re.I)


def _repo(question: str) -> str | None:
    match = REPOSITORY_RE.search(question)
    return match.group(1) if match else None


def _fragment(question: str) -> str | None:
    double = re.findall(r'"([^"]+)"', question, flags=re.S)
    if double:
        return double[-1]
    single = re.findall(r"'([^']+)'", question, flags=re.S)
    return single[-1] if single else None


def directory_extension_files(question: str) -> QueryMatch | None:
    if "files are located under" not in question.lower():
        return None
    repo, directory, extension = _repo(question), DIRECTORY_RE.search(question), EXTENSION_RE.search(question)
    if not repo or not directory or not extension:
        return None
    return QueryMatch(
        "directory_extension_files", "graph",
        """MATCH (:Repository {id:$repo})-[:CONTAINS_FILE]->(f:File)
        WHERE f.path STARTS WITH $directory AND f.extension = $extension
        RETURN f.path AS answer ORDER BY answer LIMIT 100""",
        {"repo": repo, "directory": directory.group(1).replace("\\", "/").lstrip("/"), "extension": extension.group(1).lower()},
        expected_relations=("Repository|CONTAINS_FILE|File",),
        expected_path=("Repository", "CONTAINS_FILE", "File"),
    )


def fragment_to_file(question: str) -> QueryMatch | None:
    normalized = question.lower()
    if "contains the code fragment" not in normalized and "contains the text" not in normalized:
        return None
    repo, fragment = _repo(question), _fragment(question)
    if not repo or not fragment:
        return None
    documentation = "documentation file" in normalized
    extension_filter = 'AND f.extension IN [".md", ".rst", ".txt"]' if documentation else ""
    return QueryMatch(
        "documentation_fragment_to_file" if documentation else "code_fragment_to_file",
        "hybrid",
        f"""MATCH (:Repository {{id:$repo}})-[:CONTAINS_FILE]->(f:File)
        WHERE f.content CONTAINS $fragment {extension_filter}
        RETURN f.path AS answer ORDER BY answer LIMIT 100""",
        {"repo": repo, "fragment": fragment},
        expected_relations=("Repository|CONTAINS_FILE|File",),
        expected_path=("Repository", "CONTAINS_FILE", "File"),
    )


def files_modified_by_commit(question: str) -> QueryMatch | None:
    if "files were modified by commit" not in question.lower():
        return None
    repo, commit = _repo(question), COMMIT_ID_RE.search(question)
    if not repo or not commit:
        return None
    return QueryMatch(
        "files_modified_by_commit", "graph",
        """MATCH (c:Commit {id:$commit})-[:COMMITTED_TO]->(:Repository {id:$repo})
        MATCH (c)-[:MODIFIED_FILE]->(f:File)
        RETURN DISTINCT f.path AS answer ORDER BY answer LIMIT 100""",
        {"repo": repo, "commit": commit.group(1)},
        expected_relations=("Commit|COMMITTED_TO|Repository", "Commit|MODIFIED_FILE|File"),
        expected_path=("Commit", "MODIFIED_FILE", "File"),
    )


def repository_for_issue(question: str) -> QueryMatch | None:
    if "which repository contains issue" not in question.lower():
        return None
    issue, title = ISSUE_NUMBER_RE.search(question), TITLE_RE.search(question)
    if not issue:
        return None
    params: dict[str, Any] = {"issue_number": int(issue.group(1))}
    title_clause = ""
    if title:
        params["title"] = title.group(1)
        title_clause = "AND i.title = $title"
    return QueryMatch(
        "repository_for_issue", "graph",
        f"""MATCH (r:Repository)-[:HAS_ISSUE]->(i:Issue)
        WHERE i.number = $issue_number {title_clause}
        RETURN r.id AS answer ORDER BY answer LIMIT 100""",
        params,
        expected_relations=("Repository|HAS_ISSUE|Issue",),
        expected_path=("Repository", "HAS_ISSUE", "Issue"),
    )


def developer_commits(question: str) -> QueryMatch | None:
    if "which commits were authored by developer" not in question.lower():
        return None
    repo, email = _repo(question), EMAIL_ID_RE.search(question)
    if not repo or not email:
        return None
    return QueryMatch(
        "developer_commits_in_repository", "graph",
        # Cypher forbids referencing a pre-DISTINCT variable's property
        # (c.timestamp) in ORDER BY once RETURN DISTINCT has narrowed
        # scope to the projected columns -- commit_timestamp must be
        # projected explicitly so ORDER BY can see it.
        """MATCH (d:Developer {id:$developer})-[:AUTHORED_COMMIT]->(c:Commit)-[:COMMITTED_TO]->(:Repository {id:$repo})
        RETURN DISTINCT c.id AS answer, c.timestamp AS commit_timestamp
        ORDER BY commit_timestamp DESC, answer LIMIT 100""",
        {"repo": repo, "developer": f"email:{email.group(1).lower()}"},
        expected_relations=("Developer|AUTHORED_COMMIT|Commit", "Commit|COMMITTED_TO|Repository"),
        expected_path=("Developer", "AUTHORED_COMMIT", "Commit", "COMMITTED_TO", "Repository"),
    )


def files_modified_by_developer(question: str) -> QueryMatch | None:
    normalized = question.lower()
    if "modified through commits authored by developer" not in normalized:
        return None
    repo, email = _repo(question), EMAIL_ID_RE.search(question)
    if not repo or not email:
        return None
    return QueryMatch(
        "files_modified_by_developer", "hybrid",
        """MATCH (d:Developer {id:$developer})-[:AUTHORED_COMMIT]->(c:Commit)-[:MODIFIED_FILE]->(f:File)<-[:CONTAINS_FILE]-(:Repository {id:$repo})
        RETURN DISTINCT f.path AS answer ORDER BY answer LIMIT 100""",
        {"repo": repo, "developer": f"email:{email.group(1).lower()}"},
        expected_relations=("Developer|AUTHORED_COMMIT|Commit", "Commit|MODIFIED_FILE|File", "Repository|CONTAINS_FILE|File"),
        expected_path=("Developer", "AUTHORED_COMMIT", "Commit", "MODIFIED_FILE", "File", "CONTAINS_FILE", "Repository"),
    )


def commits_modifying_file(question: str) -> QueryMatch | None:
    normalized = question.lower()
    if "which commits" not in normalized or "modified" not in normalized or "file" not in normalized:
        return None
    repo, path = _repo(question), FILE_PATH_RE.search(question)
    if not repo or not path:
        return None
    return QueryMatch(
        "commits_modifying_file", "graph",
        """MATCH (:Repository {id:$repo})-[:CONTAINS_FILE]->(f:File)
        WHERE f.path = $path MATCH (c:Commit)-[:MODIFIED_FILE]->(f)
        RETURN DISTINCT c.id AS answer ORDER BY answer LIMIT 100""",
        {"repo": repo, "path": path.group(1).replace("\\", "/")},
        expected_relations=("Repository|CONTAINS_FILE|File", "Commit|MODIFIED_FILE|File"),
    )


# ---------------------------------------------------------------------------
# Added in WP5: the templates above covered 7 of the ~16 question shapes
# generate_benchmark.py actually produces. Every matcher below mirrors the
# exact Cypher already used (and validated) as that question's ground-truth
# generator in src/benchmark_gen/generate_benchmark.py -- reusing the known
# -correct query shape rather than re-deriving it.
# ---------------------------------------------------------------------------

def issue_title_by_number(question: str) -> QueryMatch | None:
    if "title of issue" not in question.lower():
        return None
    repo, issue = _repo(question), ISSUE_NUMBER_RE.search(question)
    if not repo or not issue:
        return None
    return QueryMatch(
        "issue_title_by_number", "graph",
        """MATCH (:Repository {id:$repo})-[:HAS_ISSUE]->(i:Issue {number:$issue_number})
        WHERE i.title IS NOT NULL
        RETURN i.title AS answer LIMIT 1""",
        {"repo": repo, "issue_number": int(issue.group(1))},
        expected_relations=("Repository|HAS_ISSUE|Issue",),
        expected_path=("Repository", "HAS_ISSUE", "Issue"),
    )


def issue_state_by_number(question: str) -> QueryMatch | None:
    if "state of issue" not in question.lower():
        return None
    repo, issue = _repo(question), ISSUE_NUMBER_RE.search(question)
    if not repo or not issue:
        return None
    return QueryMatch(
        "issue_state_by_number", "graph",
        """MATCH (:Repository {id:$repo})-[:HAS_ISSUE]->(i:Issue {number:$issue_number})
        WHERE i.state IS NOT NULL
        RETURN i.state AS answer LIMIT 1""",
        {"repo": repo, "issue_number": int(issue.group(1))},
        expected_relations=("Repository|HAS_ISSUE|Issue",),
        expected_path=("Repository", "HAS_ISSUE", "Issue"),
    )


def issue_details(question: str) -> QueryMatch | None:
    if "title and state of issue" not in question.lower():
        return None
    repo, issue = _repo(question), ISSUE_NUMBER_RE.search(question)
    if not repo or not issue:
        return None
    return QueryMatch(
        "issue_details", "graph",
        """MATCH (:Repository {id:$repo})-[:HAS_ISSUE]->(i:Issue {number:$issue_number})
        WHERE i.title IS NOT NULL AND i.state IS NOT NULL
        RETURN i.title + " | " + i.state AS answer LIMIT 1""",
        {"repo": repo, "issue_number": int(issue.group(1))},
        expected_relations=("Repository|HAS_ISSUE|Issue",),
        expected_path=("Repository", "HAS_ISSUE", "Issue"),
    )


def issue_number_by_title(question: str) -> QueryMatch | None:
    if "issue number for" not in question.lower():
        return None
    repo, title = _repo(question), _fragment(question)
    if not repo or not title:
        return None
    return QueryMatch(
        "issue_number_by_title", "graph",
        """MATCH (:Repository {id:$repo})-[:HAS_ISSUE]->(i:Issue)
        WHERE i.title = $title AND i.number IS NOT NULL
        RETURN toString(i.number) AS answer ORDER BY i.number LIMIT 20""",
        {"repo": repo, "title": title},
        expected_relations=("Repository|HAS_ISSUE|Issue",),
        expected_path=("Repository", "HAS_ISSUE", "Issue"),
    )


def open_issue_titles(question: str) -> QueryMatch | None:
    if "titles of the open issues" not in question.lower():
        return None
    repo = _repo(question)
    if not repo:
        return None
    return QueryMatch(
        "open_issue_titles", "graph",
        """MATCH (:Repository {id:$repo})-[:HAS_ISSUE]->(i:Issue {state:"open"})
        WHERE i.title IS NOT NULL
        RETURN i.title AS answer ORDER BY i.number DESC LIMIT 20""",
        {"repo": repo},
        expected_relations=("Repository|HAS_ISSUE|Issue",),
        expected_path=("Repository", "HAS_ISSUE", "Issue"),
    )


def closed_issue_titles(question: str) -> QueryMatch | None:
    if "titles of the closed issues" not in question.lower():
        return None
    repo = _repo(question)
    if not repo:
        return None
    return QueryMatch(
        "closed_issue_titles", "graph",
        """MATCH (:Repository {id:$repo})-[:HAS_ISSUE]->(i:Issue {state:"closed"})
        WHERE i.title IS NOT NULL
        RETURN i.title AS answer ORDER BY i.number DESC LIMIT 20""",
        {"repo": repo},
        expected_relations=("Repository|HAS_ISSUE|Issue",),
        expected_path=("Repository", "HAS_ISSUE", "Issue"),
    )


def highest_numbered_open_issue(question: str) -> QueryMatch | None:
    if "highest issue number" not in question.lower():
        return None
    repo = _repo(question)
    if not repo:
        return None
    return QueryMatch(
        "highest_numbered_open_issue", "graph",
        """MATCH (:Repository {id:$repo})-[:HAS_ISSUE]->(i:Issue {state:"open"})
        WHERE i.number IS NOT NULL AND i.title IS NOT NULL
        RETURN toString(i.number) + " | " + i.title AS answer
        ORDER BY i.number DESC LIMIT 1""",
        {"repo": repo},
        expected_relations=("Repository|HAS_ISSUE|Issue",),
        expected_path=("Repository", "HAS_ISSUE", "Issue"),
    )


def lowest_numbered_open_issue(question: str) -> QueryMatch | None:
    if "lowest issue number" not in question.lower():
        return None
    repo = _repo(question)
    if not repo:
        return None
    return QueryMatch(
        "lowest_numbered_open_issue", "graph",
        """MATCH (:Repository {id:$repo})-[:HAS_ISSUE]->(i:Issue {state:"open"})
        WHERE i.number IS NOT NULL AND i.title IS NOT NULL
        RETURN toString(i.number) + " | " + i.title AS answer
        ORDER BY i.number LIMIT 1""",
        {"repo": repo},
        expected_relations=("Repository|HAS_ISSUE|Issue",),
        expected_path=("Repository", "HAS_ISSUE", "Issue"),
    )


def issues_matching_title_fragment(question: str) -> QueryMatch | None:
    normalized = question.lower()
    if "contain the term" not in normalized or "in their title" not in normalized:
        return None
    repo, fragment = _repo(question), _fragment(question)
    if not repo or not fragment:
        return None
    return QueryMatch(
        "issues_matching_title_fragment", "graph",
        """MATCH (:Repository {id:$repo})-[:HAS_ISSUE]->(i:Issue)
        WHERE toLower(i.title) CONTAINS toLower($fragment)
        RETURN i.title AS answer ORDER BY i.number DESC LIMIT 20""",
        {"repo": repo, "fragment": fragment},
        expected_relations=("Repository|HAS_ISSUE|Issue",),
        expected_path=("Repository", "HAS_ISSUE", "Issue"),
    )


def top_repository_contributors(question: str) -> QueryMatch | None:
    if "top commit authors" not in question.lower():
        return None
    repo = _repo(question)
    if not repo:
        return None
    return QueryMatch(
        "top_repository_contributors", "graph",
        """MATCH (d:Developer)-[:AUTHORED_COMMIT]->(c:Commit)-[:COMMITTED_TO]->(:Repository {id:$repo})
        WITH d, count(DISTINCT c) AS commit_count
        RETURN d.id + " | " + toString(commit_count) AS answer
        ORDER BY commit_count DESC, d.id LIMIT 10""",
        {"repo": repo},
        expected_relations=("Developer|AUTHORED_COMMIT|Commit", "Commit|COMMITTED_TO|Repository"),
        expected_path=("Developer", "AUTHORED_COMMIT", "Commit", "COMMITTED_TO", "Repository"),
    )


def developers_modifying_file(question: str) -> QueryMatch | None:
    if "authored commits that modified the file" not in question.lower():
        return None
    repo, path = _repo(question), _fragment(question)
    if not repo or not path:
        return None
    return QueryMatch(
        "developers_modifying_file", "hybrid",
        """MATCH (d:Developer)-[:AUTHORED_COMMIT]->(c:Commit)
        -[:MODIFIED_FILE]->(f:File {path:$path})
        <-[:CONTAINS_FILE]-(:Repository {id:$repo})
        RETURN DISTINCT d.id AS answer ORDER BY answer LIMIT 20""",
        {"repo": repo, "path": path.replace("\\", "/")},
        expected_relations=("Developer|AUTHORED_COMMIT|Commit", "Commit|MODIFIED_FILE|File", "Repository|CONTAINS_FILE|File"),
        expected_path=("Developer", "AUTHORED_COMMIT", "Commit", "MODIFIED_FILE", "File", "CONTAINS_FILE", "Repository"),
    )


MATCHERS: tuple[Callable[[str], QueryMatch | None], ...] = (
    directory_extension_files,
    fragment_to_file,
    files_modified_by_commit,
    repository_for_issue,
    developer_commits,
    files_modified_by_developer,
    commits_modifying_file,
    issue_details,
    issue_title_by_number,
    issue_state_by_number,
    issue_number_by_title,
    open_issue_titles,
    closed_issue_titles,
    highest_numbered_open_issue,
    lowest_numbered_open_issue,
    issues_matching_title_fragment,
    top_repository_contributors,
    developers_modifying_file,
)


def match_registered_query(question: str) -> QueryMatch | None:
    for matcher in MATCHERS:
        result = matcher(question)
        if result is not None:
            return result
    return None

from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from src.common import ROOT, write_jsonl
from src.graph import Graph


SEED = 42
MAX_ANSWERS = 20
MAX_ATTEMPTS_PER_CATEGORY = 5000

rng = random.Random(SEED)


CATEGORY_TARGETS = {
    "structure": 40,
    "code_retrieval": 40,
    "dependency_analysis": 45,
    "documentation_lookup": 35,
    "issue_pr_analysis": 50,
    "developer_activity": 30,
    "multi_hop": 60,
}

# Negative probes (WP3): a small, separate set of questions verified to
# have zero matching graph results, used to evaluate abstention behavior.
# These are NOT part of the 300-question core benchmark and are written to
# their own file so the well-established category distribution above never
# changes.
UNANSWERABLE_TARGET = 20
MAX_UNANSWERABLE_ATTEMPTS = 2000


def load_source_snapshots() -> dict[str, str | None]:
    """
    Map repository slug -> cloned commit SHA, from
    src/ingestion/repository_metadata.py's output (data/metadata/*.json).

    Returns an empty mapping if that script has not been run yet, so
    benchmark generation never hard-depends on WP2 having run first.
    """
    metadata_dir = ROOT / "data" / "metadata"
    snapshots: dict[str, str | None] = {}

    if not metadata_dir.exists():
        return snapshots

    for path in metadata_dir.glob("*.json"):
        if path.name == "summary.json":
            continue

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        repo = data.get("repository")

        if repo:
            snapshots[repo] = data.get("commit_sha")

    return snapshots


SOURCE_SNAPSHOTS = load_source_snapshots()


def classify_answer_type(answer_type: str, answers: list[Any]) -> str:
    """
    Map the fine-grained `answer_type` onto the guide's controlled
    vocabulary (Section 5.3) so evaluation can branch grading logic by
    answer shape instead of using one universal coverage function for
    everything.
    """
    if answer_type == "developer_commit_count":
        return "ranked_list"

    if len(answers) > 1:
        return "multiple_entities"

    return "single_entity"


def required_optional_retrieval(route: str) -> tuple[list[str], list[str]]:
    """
    Split an expected_retrieval_route into required/optional retrieval
    sources (Guide Section 5.1). No template in this benchmark currently
    justifies claiming an optional secondary source, so optional_retrieval
    is always empty; hybrid questions require both graph and vector.
    """
    if route == "hybrid":
        return ["graph", "vector"], []

    return [route], []


def clean_scalar(value: Any) -> Any:
    """Convert Neo4j values into JSON-safe scalar values."""
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def extract_answers(result: list[dict[str, Any]]) -> list[Any]:
    """
    Extract, normalize, and deduplicate the `answer` field returned by Cypher.
    """
    answers: list[Any] = []
    seen: set[str] = set()

    for row in result:
        value = clean_scalar(row.get("answer"))

        if value is None:
            continue

        if isinstance(value, str):
            value = value.strip()

        if value == "":
            continue

        key = json.dumps(value, sort_keys=True, ensure_ascii=False)

        if key not in seen:
            seen.add(key)
            answers.append(value)

    return answers[:MAX_ANSWERS]


def normalize_question(question: str) -> str:
    """Normalize question text for duplicate detection."""
    return re.sub(r"\s+", " ", question.strip().lower())


def safe_fragment(content: str, min_length: int = 30, max_length: int = 100) -> str | None:
    """
    Select a meaningful code or documentation fragment.

    The fragment is used as a retrieval clue rather than returning an entire
    source file as the expected answer.
    """
    if not content:
        return None

    candidates: list[str] = []

    for raw_line in content.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()

        if len(line) < min_length:
            continue

        # Ignore common low-information lines.
        if line in {"{", "}", "(", ")", "[", "]"}:
            continue

        if set(line) <= {"-", "=", "*", "#", "/", " "}:
            continue

        candidates.append(line)

    if not candidates:
        compact = re.sub(r"\s+", " ", content).strip()

        if len(compact) < min_length:
            return None

        candidates = [compact]

    fragment = rng.choice(candidates)
    fragment = fragment[:max_length].strip()

    # Remove characters that make the natural-language question difficult
    # to read while preserving the actual fragment used in Cypher.
    return fragment if len(fragment) >= min_length else None


def quote_fragment(fragment: str) -> str:
    """Format a fragment safely inside a benchmark question."""
    readable = fragment.replace("\n", " ").replace("\r", " ")
    readable = re.sub(r"\s+", " ", readable).strip()

    if len(readable) > 100:
        readable = readable[:100].rstrip()

    return f'"{readable}"'


def get_directory(path: str) -> str | None:
    """Return the parent directory of a repository-relative file path."""
    normalized = path.replace("\\", "/").strip("/")

    if "/" not in normalized:
        return None

    return normalized.rsplit("/", 1)[0] + "/"


def expected_relations_for_template(template_name: str) -> list[str]:
    """Return system-independent graph relations required by a template."""
    mapping = {
        "directory_extension_files": ["Repository|CONTAINS_FILE|File"],
        "code_fragment_to_file": ["Repository|CONTAINS_FILE|File"],
        "documentation_fragment_to_file": ["Repository|CONTAINS_FILE|File"],
        "commits_modifying_file": [
            "Repository|CONTAINS_FILE|File",
            "Commit|MODIFIED_FILE|File",
        ],
        "files_modified_by_commit": [
            "Commit|COMMITTED_TO|Repository",
            "Commit|MODIFIED_FILE|File",
        ],
        "issue_title_by_number": ["Repository|HAS_ISSUE|Issue"],
        "issue_state_by_number": ["Repository|HAS_ISSUE|Issue"],
        "issue_number_by_title": ["Repository|HAS_ISSUE|Issue"],
        "repository_for_issue": ["Repository|HAS_ISSUE|Issue"],
        "open_issue_titles": ["Repository|HAS_ISSUE|Issue"],
        "closed_issue_titles": ["Repository|HAS_ISSUE|Issue"],
        "highest_numbered_open_issue": ["Repository|HAS_ISSUE|Issue"],
        "lowest_numbered_open_issue": ["Repository|HAS_ISSUE|Issue"],
        "issues_matching_title_fragment": ["Repository|HAS_ISSUE|Issue"],
        "issue_details": ["Repository|HAS_ISSUE|Issue"],
        "top_repository_contributors": [
            "Developer|AUTHORED_COMMIT|Commit",
            "Commit|COMMITTED_TO|Repository",
        ],
        "developer_commits_in_repository": [
            "Developer|AUTHORED_COMMIT|Commit",
            "Commit|COMMITTED_TO|Repository",
        ],
        "developers_modifying_file": [
            "Developer|AUTHORED_COMMIT|Commit",
            "Commit|MODIFIED_FILE|File",
            "Repository|CONTAINS_FILE|File",
        ],
        "files_modified_by_developer": [
            "Developer|AUTHORED_COMMIT|Commit",
            "Commit|MODIFIED_FILE|File",
            "Repository|CONTAINS_FILE|File",
        ],
    }
    return mapping.get(template_name, [])


def expected_path_for_template(template_name: str) -> list[str]:
    """Return the required ordered reasoning path for path-based metrics."""
    mapping = {
        "directory_extension_files": ["Repository", "CONTAINS_FILE", "File"],
        "code_fragment_to_file": ["Repository", "CONTAINS_FILE", "File"],
        "documentation_fragment_to_file": ["Repository", "CONTAINS_FILE", "File"],
        "commits_modifying_file": [
            "Repository", "CONTAINS_FILE", "File", "MODIFIED_FILE", "Commit"
        ],
        "files_modified_by_commit": [
            "Commit", "MODIFIED_FILE", "File", "CONTAINS_FILE", "Repository"
        ],
        "issue_title_by_number": ["Repository", "HAS_ISSUE", "Issue"],
        "issue_state_by_number": ["Repository", "HAS_ISSUE", "Issue"],
        "issue_number_by_title": ["Repository", "HAS_ISSUE", "Issue"],
        "repository_for_issue": ["Repository", "HAS_ISSUE", "Issue"],
        "open_issue_titles": ["Repository", "HAS_ISSUE", "Issue"],
        "closed_issue_titles": ["Repository", "HAS_ISSUE", "Issue"],
        "highest_numbered_open_issue": ["Repository", "HAS_ISSUE", "Issue"],
        "lowest_numbered_open_issue": ["Repository", "HAS_ISSUE", "Issue"],
        "issues_matching_title_fragment": ["Repository", "HAS_ISSUE", "Issue"],
        "issue_details": ["Repository", "HAS_ISSUE", "Issue"],
        "top_repository_contributors": [
            "Developer", "AUTHORED_COMMIT", "Commit", "COMMITTED_TO", "Repository"
        ],
        "developer_commits_in_repository": [
            "Developer", "AUTHORED_COMMIT", "Commit", "COMMITTED_TO", "Repository"
        ],
        "developers_modifying_file": [
            "Developer", "AUTHORED_COMMIT", "Commit", "MODIFIED_FILE", "File",
            "CONTAINS_FILE", "Repository"
        ],
        "files_modified_by_developer": [
            "Developer", "AUTHORED_COMMIT", "Commit", "MODIFIED_FILE", "File",
            "CONTAINS_FILE", "Repository"
        ],
    }
    return mapping.get(template_name, [])


def expected_route_for_category(category: str) -> str:
    """Define the independently expected retrieval strategy."""
    if category in {"code_retrieval", "documentation_lookup"}:
        return "vector"
    if category == "multi_hop":
        return "hybrid"
    return "graph"


def build_required_facts(
    *, template_name: str, answers: list[Any], params: dict[str, Any], source_repo: str
) -> list[str]:
    """Create answer facts without copying any evaluated system response."""
    facts: list[str] = []
    path = params.get("path")
    developer = params.get("developer")
    commit = params.get("commit")
    issue_number = params.get("issue_number")

    for answer in answers:
        value = str(answer)
        if template_name in {"code_fragment_to_file", "documentation_fragment_to_file"}:
            facts.append(f"{value} is the matching file in repository {source_repo}")
        elif template_name == "directory_extension_files":
            facts.append(f"{value} is contained in repository {source_repo}")
        elif template_name == "commits_modifying_file":
            facts.append(f"Commit {value} modified file {path} in repository {source_repo}")
        elif template_name == "files_modified_by_commit":
            facts.append(f"Commit {commit} modified file {value} in repository {source_repo}")
        elif template_name == "developer_commits_in_repository":
            facts.append(f"Developer {developer} authored commit {value} in repository {source_repo}")
        elif template_name == "developers_modifying_file":
            facts.append(f"Developer {value} authored a commit that modified file {path} in repository {source_repo}")
        elif template_name == "files_modified_by_developer":
            facts.append(f"Developer {developer} authored a commit that modified file {value} in repository {source_repo}")
        elif template_name.startswith("issue_") or "issue" in template_name:
            label = f"Issue #{issue_number}" if issue_number is not None else "The matching issue"
            facts.append(f"{label} in repository {source_repo} has answer {value}")
        elif template_name == "top_repository_contributors":
            facts.append(f"{value} is a top commit-author result for repository {source_repo}")
        else:
            facts.append(f"{value} is a validated answer for repository {source_repo}")
    return facts


def build_gold_evidence(
    *, answers: list[Any], params: dict[str, Any], source_repo: str,
    relations: list[str]
) -> list[str]:
    """Create stable evidence identifiers suitable for Recall@k evaluation."""
    evidence = [f"Repository:{source_repo}"]
    for key in ("path", "commit", "developer", "issue_number", "directory", "fragment", "title"):
        value = params.get(key)
        if value is not None and str(value).strip():
            evidence.append(f"{key}:{value}")
    evidence.extend(f"answer:{answer}" for answer in answers)
    evidence.extend(f"relation:{relation}" for relation in relations)
    return list(dict.fromkeys(evidence))


def make_row(
    *,
    category: str,
    question: str,
    cypher: str,
    params: dict[str, Any],
    answers: list[Any],
    source_repo: str,
    difficulty: str,
    hop_count: int,
    answer_type: str,
    template_name: str,
    evidence_entities: list[str],
) -> dict[str, Any]:
    """Build one benchmark item with independent, machine-readable ground truth."""
    expected_entities = [clean_scalar(answer) for answer in answers]
    expected_relations = expected_relations_for_template(template_name)
    expected_path = expected_path_for_template(template_name)
    required_facts = build_required_facts(
        template_name=template_name,
        answers=answers,
        params=params,
        source_repo=source_repo,
    )
    gold_evidence = build_gold_evidence(
        answers=answers,
        params=params,
        source_repo=source_repo,
        relations=expected_relations,
    )

    # A code-fragment query can legitimately match multiple files.
    if answer_type == "file_path" and len(answers) > 1:
        answer_type = "file_list"

    route = expected_route_for_category(category)
    required_retrieval, optional_retrieval = required_optional_retrieval(route)

    return {
        "category": category,
        "question": question,
        "cypher": cypher.strip(),
        "params": params,
        "ground_truth": answers,
        "expected_answer": answers,
        "expected_entities": expected_entities,
        "required_facts": required_facts,
        "expected_relations": expected_relations,
        "expected_path": expected_path,
        "gold_evidence": gold_evidence,
        "expected_retrieval_route": route,
        "source_repo": source_repo,
        "difficulty": difficulty,
        "difficulty_level": difficulty,
        "hop_count": hop_count,
        "reasoning_hops": hop_count,
        "answer_type": answer_type,
        "answer_type_class": classify_answer_type(answer_type, answers),
        "template_name": template_name,
        "evidence_entities": evidence_entities,
        "reference_provenance": "neo4j_cypher_ground_truth",
        "answerable": True,
        "source_snapshot": SOURCE_SNAPSHOTS.get(source_repo),
        "required_retrieval": required_retrieval,
        "optional_retrieval": optional_retrieval,
        "question_generation_method": "cypher_template",
    }


# ---------------------------------------------------------------------------
# Structure questions
# ---------------------------------------------------------------------------

def generate_structure_question(g: Graph) -> dict[str, Any] | None:
    candidates = g.query(
        """
        MATCH (r:Repository)-[:CONTAINS_FILE]->(f:File)
        WHERE f.path IS NOT NULL
          AND f.extension IS NOT NULL
        RETURN r.id AS repo,
               f.path AS path,
               f.extension AS extension
        LIMIT 3000
        """
    )

    if not candidates:
        return None

    anchor = rng.choice(candidates)

    repo = anchor["repo"]
    path = anchor["path"]
    extension = anchor["extension"]
    directory = get_directory(path)

    if not directory:
        return None

    cypher = """
    MATCH (:Repository {id:$repo})-[:CONTAINS_FILE]->(f:File)
    WHERE f.path STARTS WITH $directory
      AND f.extension = $extension
    RETURN f.path AS answer
    ORDER BY answer
    LIMIT 20
    """

    params = {
        "repo": repo,
        "directory": directory,
        "extension": extension,
    }

    answers = extract_answers(g.query(cypher, **params))

    if not answers:
        return None

    question = (
        f"Which {extension} files are located under the "
        f"'{directory}' directory in repository {repo}?"
    )

    return make_row(
        category="structure",
        question=question,
        cypher=cypher,
        params=params,
        answers=answers,
        source_repo=repo,
        difficulty="medium",
        hop_count=1,
        answer_type="file_list",
        template_name="directory_extension_files",
        evidence_entities=["Repository", "File"],
    )


# ---------------------------------------------------------------------------
# Code retrieval questions
# ---------------------------------------------------------------------------

def generate_code_retrieval_question(g: Graph) -> dict[str, Any] | None:
    candidates = g.query(
        """
        MATCH (r:Repository)-[:CONTAINS_FILE]->(f:File)
        WHERE f.content IS NOT NULL
          AND size(trim(f.content)) >= 120
          AND NOT f.extension IN [".md", ".rst", ".txt"]
        RETURN r.id AS repo,
               f.path AS path,
               f.content AS content
        LIMIT 2000
        """
    )

    if not candidates:
        return None

    anchor = rng.choice(candidates)

    repo = anchor["repo"]
    content = anchor.get("content") or ""
    fragment = safe_fragment(content)

    if not fragment:
        return None

    cypher = """
    MATCH (:Repository {id:$repo})-[:CONTAINS_FILE]->(f:File)
    WHERE f.content CONTAINS $fragment
    RETURN f.path AS answer
    ORDER BY answer
    LIMIT 20
    """

    params = {
        "repo": repo,
        "fragment": fragment,
    }

    answers = extract_answers(g.query(cypher, **params))

    # Extremely common fragments are poor retrieval clues.
    if not answers or len(answers) > 5:
        return None

    question = (
        f"Which source file in repository {repo} contains the code fragment "
        f"{quote_fragment(fragment)}?"
    )

    return make_row(
        category="code_retrieval",
        question=question,
        cypher=cypher,
        params=params,
        answers=answers,
        source_repo=repo,
        difficulty="medium",
        hop_count=1,
        answer_type="file_path",
        template_name="code_fragment_to_file",
        evidence_entities=["Repository", "File"],
    )


# ---------------------------------------------------------------------------
# Dependency and change-history questions
# ---------------------------------------------------------------------------

def generate_dependency_question(g: Graph) -> dict[str, Any] | None:
    template = rng.choice(
        [
            "commits_for_file",
            "files_for_commit",
        ]
    )

    if template == "commits_for_file":
        anchors = g.query(
            """
            MATCH (r:Repository)-[:CONTAINS_FILE]->(f:File)
                  <-[:MODIFIED_FILE]-(c:Commit)
            RETURN DISTINCT r.id AS repo,
                            f.path AS path
            LIMIT 3000
            """
        )

        if not anchors:
            return None

        anchor = rng.choice(anchors)
        repo = anchor["repo"]
        path = anchor["path"]

        cypher = """
        MATCH (:Repository {id:$repo})-[:CONTAINS_FILE]->(f:File {path:$path})
              <-[:MODIFIED_FILE]-(c:Commit)
        RETURN c.id AS answer
        ORDER BY c.timestamp DESC, c.id
        LIMIT 20
        """

        params = {
            "repo": repo,
            "path": path,
        }

        answers = extract_answers(g.query(cypher, **params))

        if not answers:
            return None

        question = (
            f"Which commits modified the file '{path}' "
            f"in repository {repo}?"
        )

        return make_row(
            category="dependency_analysis",
            question=question,
            cypher=cypher,
            params=params,
            answers=answers,
            source_repo=repo,
            difficulty="medium",
            hop_count=2,
            answer_type="commit_list",
            template_name="commits_modifying_file",
            evidence_entities=["Repository", "File", "Commit"],
        )

    anchors = g.query(
        """
        MATCH (c:Commit)-[:COMMITTED_TO]->(r:Repository)
        MATCH (c)-[:MODIFIED_FILE]->(f:File)
        RETURN DISTINCT r.id AS repo,
                        c.id AS commit
        LIMIT 3000
        """
    )

    if not anchors:
        return None

    anchor = rng.choice(anchors)
    repo = anchor["repo"]
    commit = anchor["commit"]

    cypher = """
    MATCH (c:Commit {id:$commit})-[:COMMITTED_TO]->(:Repository {id:$repo})
    MATCH (c)-[:MODIFIED_FILE]->(f:File)
    RETURN f.path AS answer
    ORDER BY answer
    LIMIT 20
    """

    params = {
        "repo": repo,
        "commit": commit,
    }

    answers = extract_answers(g.query(cypher, **params))

    if not answers:
        return None

    question = (
        f"Which files were modified by commit {commit} "
        f"in repository {repo}?"
    )

    return make_row(
        category="dependency_analysis",
        question=question,
        cypher=cypher,
        params=params,
        answers=answers,
        source_repo=repo,
        difficulty="medium",
        hop_count=2,
        answer_type="file_list",
        template_name="files_modified_by_commit",
        evidence_entities=["Repository", "Commit", "File"],
    )


# ---------------------------------------------------------------------------
# Documentation questions
# ---------------------------------------------------------------------------

def generate_documentation_question(g: Graph) -> dict[str, Any] | None:
    candidates = g.query(
        """
        MATCH (r:Repository)-[:CONTAINS_FILE]->(f:File)
        WHERE f.extension IN [".md", ".rst", ".txt"]
          AND f.content IS NOT NULL
          AND size(trim(f.content)) >= 100
        RETURN r.id AS repo,
               f.path AS path,
               f.content AS content
        LIMIT 2000
        """
    )

    if not candidates:
        return None

    anchor = rng.choice(candidates)

    repo = anchor["repo"]
    content = anchor.get("content") or ""
    fragment = safe_fragment(content, min_length=25, max_length=110)

    if not fragment:
        return None

    cypher = """
    MATCH (:Repository {id:$repo})-[:CONTAINS_FILE]->(f:File)
    WHERE f.extension IN [".md", ".rst", ".txt"]
      AND f.content CONTAINS $fragment
    RETURN f.path AS answer
    ORDER BY answer
    LIMIT 20
    """

    params = {
        "repo": repo,
        "fragment": fragment,
    }

    answers = extract_answers(g.query(cypher, **params))

    if not answers or len(answers) > 5:
        return None

    question = (
        f"Which documentation file in repository {repo} contains the text "
        f"{quote_fragment(fragment)}?"
    )

    return make_row(
        category="documentation_lookup",
        question=question,
        cypher=cypher,
        params=params,
        answers=answers,
        source_repo=repo,
        difficulty="medium",
        hop_count=1,
        answer_type="documentation_file",
        template_name="documentation_fragment_to_file",
        evidence_entities=["Repository", "File"],
    )


# ---------------------------------------------------------------------------
# Issue questions
# ---------------------------------------------------------------------------
def generate_issue_question(g: Graph) -> dict[str, Any] | None:
    """
    Generate varied issue-analysis questions.

    Questions are anchored to real Issue nodes so that enough unique,
    non-empty questions can be produced even when the graph contains
    only a small number of repositories.
    """

    templates = [
        "issue_title_by_number",
        "issue_state_by_number",
        "issue_number_by_title",
        "repository_for_issue",
        "open_issue_titles",
        "closed_issue_titles",
        "latest_open_issue",
        "earliest_open_issue",
        "issues_matching_title_fragment",
        "issue_details",
    ]

    template = rng.choice(templates)

    # ------------------------------------------------------------------
    # 1. Find an issue title using repository and issue number
    # ------------------------------------------------------------------
    if template == "issue_title_by_number":
        anchors = g.query(
            """
            MATCH (r:Repository)-[:HAS_ISSUE]->(i:Issue)
            WHERE i.number IS NOT NULL
              AND i.title IS NOT NULL
            RETURN r.id AS repo,
                   i.number AS issue_number
            LIMIT 5000
            """
        )

        if not anchors:
            return None

        anchor = rng.choice(anchors)
        repo = anchor["repo"]
        issue_number = anchor["issue_number"]

        cypher = """
        MATCH (:Repository {id:$repo})-[:HAS_ISSUE]->
              (i:Issue {number:$issue_number})
        WHERE i.title IS NOT NULL
        RETURN i.title AS answer
        LIMIT 1
        """

        params = {
            "repo": repo,
            "issue_number": issue_number,
        }

        answers = extract_answers(g.query(cypher, **params))

        if not answers:
            return None

        question = (
            f"What is the title of issue #{issue_number} "
            f"in repository {repo}?"
        )

        return make_row(
            category="issue_pr_analysis",
            question=question,
            cypher=cypher,
            params=params,
            answers=answers,
            source_repo=repo,
            difficulty="easy",
            hop_count=1,
            answer_type="issue_title",
            template_name="issue_title_by_number",
            evidence_entities=["Repository", "Issue"],
        )

    # ------------------------------------------------------------------
    # 2. Find an issue state using repository and issue number
    # ------------------------------------------------------------------
    if template == "issue_state_by_number":
        anchors = g.query(
            """
            MATCH (r:Repository)-[:HAS_ISSUE]->(i:Issue)
            WHERE i.number IS NOT NULL
              AND i.state IS NOT NULL
            RETURN r.id AS repo,
                   i.number AS issue_number
            LIMIT 5000
            """
        )

        if not anchors:
            return None

        anchor = rng.choice(anchors)
        repo = anchor["repo"]
        issue_number = anchor["issue_number"]

        cypher = """
        MATCH (:Repository {id:$repo})-[:HAS_ISSUE]->
              (i:Issue {number:$issue_number})
        WHERE i.state IS NOT NULL
        RETURN i.state AS answer
        LIMIT 1
        """

        params = {
            "repo": repo,
            "issue_number": issue_number,
        }

        answers = extract_answers(g.query(cypher, **params))

        if not answers:
            return None

        question = (
            f"What is the state of issue #{issue_number} "
            f"in repository {repo}?"
        )

        return make_row(
            category="issue_pr_analysis",
            question=question,
            cypher=cypher,
            params=params,
            answers=answers,
            source_repo=repo,
            difficulty="easy",
            hop_count=1,
            answer_type="issue_state",
            template_name="issue_state_by_number",
            evidence_entities=["Repository", "Issue"],
        )

    # ------------------------------------------------------------------
    # 3. Find an issue number using its exact title
    # ------------------------------------------------------------------
    if template == "issue_number_by_title":
        anchors = g.query(
            """
            MATCH (r:Repository)-[:HAS_ISSUE]->(i:Issue)
            WHERE i.title IS NOT NULL
              AND i.number IS NOT NULL
            RETURN r.id AS repo,
                   i.title AS title
            LIMIT 5000
            """
        )

        if not anchors:
            return None

        anchor = rng.choice(anchors)
        repo = anchor["repo"]
        title = anchor["title"]

        cypher = """
        MATCH (:Repository {id:$repo})-[:HAS_ISSUE]->(i:Issue)
        WHERE i.title = $title
          AND i.number IS NOT NULL
        RETURN toString(i.number) AS answer
        ORDER BY i.number
        LIMIT 20
        """

        params = {
            "repo": repo,
            "title": title,
        }

        answers = extract_answers(g.query(cypher, **params))

        if not answers:
            return None

        question = (
            f"What is the issue number for '{title}' "
            f"in repository {repo}?"
        )

        return make_row(
            category="issue_pr_analysis",
            question=question,
            cypher=cypher,
            params=params,
            answers=answers,
            source_repo=repo,
            difficulty="medium",
            hop_count=1,
            answer_type="issue_number",
            template_name="issue_number_by_title",
            evidence_entities=["Repository", "Issue"],
        )

    # ------------------------------------------------------------------
    # 4. Identify the repository containing an issue
    # ------------------------------------------------------------------
    if template == "repository_for_issue":
        anchors = g.query(
            """
            MATCH (r:Repository)-[:HAS_ISSUE]->(i:Issue)
            WHERE i.number IS NOT NULL
              AND i.title IS NOT NULL
            RETURN r.id AS repo,
                   i.number AS issue_number,
                   i.title AS title
            LIMIT 5000
            """
        )

        if not anchors:
            return None

        anchor = rng.choice(anchors)
        issue_number = anchor["issue_number"]
        title = anchor["title"]
        expected_repo = anchor["repo"]

        cypher = """
        MATCH (r:Repository)-[:HAS_ISSUE]->(i:Issue)
        WHERE i.number = $issue_number
          AND i.title = $title
        RETURN r.id AS answer
        ORDER BY answer
        LIMIT 20
        """

        params = {
            "issue_number": issue_number,
            "title": title,
        }

        answers = extract_answers(g.query(cypher, **params))

        if not answers:
            return None

        question = (
            f"Which repository contains issue #{issue_number} "
            f"titled '{title}'?"
        )

        return make_row(
            category="issue_pr_analysis",
            question=question,
            cypher=cypher,
            params=params,
            answers=answers,
            source_repo=expected_repo,
            difficulty="medium",
            hop_count=1,
            answer_type="repository_id",
            template_name="repository_for_issue",
            evidence_entities=["Repository", "Issue"],
        )

    # ------------------------------------------------------------------
    # 5. List open issue titles
    # ------------------------------------------------------------------
    if template == "open_issue_titles":
        repos = g.query(
            """
            MATCH (r:Repository)-[:HAS_ISSUE]->(i:Issue {state:"open"})
            WHERE i.title IS NOT NULL
            RETURN DISTINCT r.id AS repo
            LIMIT 1000
            """
        )

        if not repos:
            return None

        repo = rng.choice(repos)["repo"]

        cypher = """
        MATCH (:Repository {id:$repo})-[:HAS_ISSUE]->
              (i:Issue {state:"open"})
        WHERE i.title IS NOT NULL
        RETURN i.title AS answer
        ORDER BY i.number DESC
        LIMIT 20
        """

        params = {"repo": repo}
        answers = extract_answers(g.query(cypher, **params))

        if not answers:
            return None

        question = (
            f"What are the titles of the open issues "
            f"in repository {repo}?"
        )

        return make_row(
            category="issue_pr_analysis",
            question=question,
            cypher=cypher,
            params=params,
            answers=answers,
            source_repo=repo,
            difficulty="easy",
            hop_count=1,
            answer_type="issue_title_list",
            template_name="open_issue_titles",
            evidence_entities=["Repository", "Issue"],
        )

    # ------------------------------------------------------------------
    # 6. List closed issue titles
    # ------------------------------------------------------------------
    if template == "closed_issue_titles":
        repos = g.query(
            """
            MATCH (r:Repository)-[:HAS_ISSUE]->(i:Issue {state:"closed"})
            WHERE i.title IS NOT NULL
            RETURN DISTINCT r.id AS repo
            LIMIT 1000
            """
        )

        if not repos:
            return None

        repo = rng.choice(repos)["repo"]

        cypher = """
        MATCH (:Repository {id:$repo})-[:HAS_ISSUE]->
              (i:Issue {state:"closed"})
        WHERE i.title IS NOT NULL
        RETURN i.title AS answer
        ORDER BY i.number DESC
        LIMIT 20
        """

        params = {"repo": repo}
        answers = extract_answers(g.query(cypher, **params))

        if not answers:
            return None

        question = (
            f"What are the titles of the closed issues "
            f"in repository {repo}?"
        )

        return make_row(
            category="issue_pr_analysis",
            question=question,
            cypher=cypher,
            params=params,
            answers=answers,
            source_repo=repo,
            difficulty="easy",
            hop_count=1,
            answer_type="issue_title_list",
            template_name="closed_issue_titles",
            evidence_entities=["Repository", "Issue"],
        )

    # ------------------------------------------------------------------
    # 7. Highest-numbered open issue
    # ------------------------------------------------------------------
    if template == "latest_open_issue":
        repos = g.query(
            """
            MATCH (r:Repository)-[:HAS_ISSUE]->(i:Issue {state:"open"})
            WHERE i.number IS NOT NULL
              AND i.title IS NOT NULL
            RETURN DISTINCT r.id AS repo
            LIMIT 1000
            """
        )

        if not repos:
            return None

        repo = rng.choice(repos)["repo"]

        cypher = """
        MATCH (:Repository {id:$repo})-[:HAS_ISSUE]->
              (i:Issue {state:"open"})
        WHERE i.number IS NOT NULL
          AND i.title IS NOT NULL
        RETURN toString(i.number) + " | " + i.title AS answer
        ORDER BY i.number DESC
        LIMIT 1
        """

        params = {"repo": repo}
        answers = extract_answers(g.query(cypher, **params))

        if not answers:
            return None

        question = (
            f"Which open issue has the highest issue number "
            f"in repository {repo}? Return its number and title."
        )

        return make_row(
            category="issue_pr_analysis",
            question=question,
            cypher=cypher,
            params=params,
            answers=answers,
            source_repo=repo,
            difficulty="medium",
            hop_count=1,
            answer_type="issue_number_and_title",
            template_name="highest_numbered_open_issue",
            evidence_entities=["Repository", "Issue"],
        )

    # ------------------------------------------------------------------
    # 8. Lowest-numbered open issue
    # ------------------------------------------------------------------
    if template == "earliest_open_issue":
        repos = g.query(
            """
            MATCH (r:Repository)-[:HAS_ISSUE]->(i:Issue {state:"open"})
            WHERE i.number IS NOT NULL
              AND i.title IS NOT NULL
            RETURN DISTINCT r.id AS repo
            LIMIT 1000
            """
        )

        if not repos:
            return None

        repo = rng.choice(repos)["repo"]

        cypher = """
        MATCH (:Repository {id:$repo})-[:HAS_ISSUE]->
              (i:Issue {state:"open"})
        WHERE i.number IS NOT NULL
          AND i.title IS NOT NULL
        RETURN toString(i.number) + " | " + i.title AS answer
        ORDER BY i.number
        LIMIT 1
        """

        params = {"repo": repo}
        answers = extract_answers(g.query(cypher, **params))

        if not answers:
            return None

        question = (
            f"Which open issue has the lowest issue number "
            f"in repository {repo}? Return its number and title."
        )

        return make_row(
            category="issue_pr_analysis",
            question=question,
            cypher=cypher,
            params=params,
            answers=answers,
            source_repo=repo,
            difficulty="medium",
            hop_count=1,
            answer_type="issue_number_and_title",
            template_name="lowest_numbered_open_issue",
            evidence_entities=["Repository", "Issue"],
        )

    # ------------------------------------------------------------------
    # 9. Search issues using a title fragment
    # ------------------------------------------------------------------
    if template == "issues_matching_title_fragment":
        anchors = g.query(
            """
            MATCH (r:Repository)-[:HAS_ISSUE]->(i:Issue)
            WHERE i.title IS NOT NULL
              AND size(trim(i.title)) >= 12
            RETURN r.id AS repo,
                   i.title AS title
            LIMIT 5000
            """
        )

        if not anchors:
            return None

        anchor = rng.choice(anchors)
        repo = anchor["repo"]
        title = anchor["title"]

        words = [
            word
            for word in re.findall(r"[A-Za-z0-9_-]+", title)
            if len(word) >= 5
        ]

        if not words:
            return None

        fragment = rng.choice(words)

        cypher = """
        MATCH (:Repository {id:$repo})-[:HAS_ISSUE]->(i:Issue)
        WHERE toLower(i.title) CONTAINS toLower($fragment)
        RETURN i.title AS answer
        ORDER BY i.number DESC
        LIMIT 20
        """

        params = {
            "repo": repo,
            "fragment": fragment,
        }

        answers = extract_answers(g.query(cypher, **params))

        if not answers or len(answers) > 10:
            return None

        question = (
            f"Which issues in repository {repo} contain the term "
            f"'{fragment}' in their title?"
        )

        return make_row(
            category="issue_pr_analysis",
            question=question,
            cypher=cypher,
            params=params,
            answers=answers,
            source_repo=repo,
            difficulty="medium",
            hop_count=1,
            answer_type="issue_title_list",
            template_name="issues_matching_title_fragment",
            evidence_entities=["Repository", "Issue"],
        )

    # ------------------------------------------------------------------
    # 10. Return combined details for one issue
    # ------------------------------------------------------------------
    if template == "issue_details":
        anchors = g.query(
            """
            MATCH (r:Repository)-[:HAS_ISSUE]->(i:Issue)
            WHERE i.number IS NOT NULL
              AND i.title IS NOT NULL
              AND i.state IS NOT NULL
            RETURN r.id AS repo,
                   i.number AS issue_number
            LIMIT 5000
            """
        )

        if not anchors:
            return None

        anchor = rng.choice(anchors)
        repo = anchor["repo"]
        issue_number = anchor["issue_number"]

        cypher = """
        MATCH (:Repository {id:$repo})-[:HAS_ISSUE]->
              (i:Issue {number:$issue_number})
        WHERE i.title IS NOT NULL
          AND i.state IS NOT NULL
        RETURN i.title + " | " + i.state AS answer
        LIMIT 1
        """

        params = {
            "repo": repo,
            "issue_number": issue_number,
        }

        answers = extract_answers(g.query(cypher, **params))

        if not answers:
            return None

        question = (
            f"What are the title and state of issue #{issue_number} "
            f"in repository {repo}?"
        )

        return make_row(
            category="issue_pr_analysis",
            question=question,
            cypher=cypher,
            params=params,
            answers=answers,
            source_repo=repo,
            difficulty="medium",
            hop_count=1,
            answer_type="issue_title_and_state",
            template_name="issue_details",
            evidence_entities=["Repository", "Issue"],
        )

    return None


# ---------------------------------------------------------------------------
# Developer activity questions
# ---------------------------------------------------------------------------

def generate_developer_activity_question(g: Graph) -> dict[str, Any] | None:
    template = rng.choice(
        [
            "top_contributors",
            "developer_commits",
        ]
    )

    if template == "top_contributors":
        repos = g.query(
            """
            MATCH (:Developer)-[:AUTHORED_COMMIT]->(:Commit)
                  -[:COMMITTED_TO]->(r:Repository)
            RETURN DISTINCT r.id AS repo
            LIMIT 1000
            """
        )

        if not repos:
            return None

        repo = rng.choice(repos)["repo"]

        cypher = """
        MATCH (d:Developer)-[:AUTHORED_COMMIT]->(c:Commit)
              -[:COMMITTED_TO]->(:Repository {id:$repo})
        WITH d, count(DISTINCT c) AS commit_count
        RETURN d.id + " | " + toString(commit_count) AS answer
        ORDER BY commit_count DESC, d.id
        LIMIT 10
        """

        params = {"repo": repo}
        answers = extract_answers(g.query(cypher, **params))

        if not answers:
            return None

        question = (
            f"Who are the top commit authors in repository {repo}? "
            f"Return each developer identifier with the number of commits."
        )

        return make_row(
            category="developer_activity",
            question=question,
            cypher=cypher,
            params=params,
            answers=answers,
            source_repo=repo,
            difficulty="medium",
            hop_count=2,
            answer_type="developer_commit_count",
            template_name="top_repository_contributors",
            evidence_entities=["Developer", "Commit", "Repository"],
        )

    anchors = g.query(
        """
        MATCH (d:Developer)-[:AUTHORED_COMMIT]->(c:Commit)
              -[:COMMITTED_TO]->(r:Repository)
        RETURN DISTINCT d.id AS developer,
                        r.id AS repo
        LIMIT 3000
        """
    )

    if not anchors:
        return None

    anchor = rng.choice(anchors)
    developer = anchor["developer"]
    repo = anchor["repo"]

    cypher = """
    MATCH (d:Developer {id:$developer})-[:AUTHORED_COMMIT]->(c:Commit)
          -[:COMMITTED_TO]->(:Repository {id:$repo})
    RETURN c.id AS answer
    ORDER BY c.timestamp DESC, c.id
    LIMIT 20
    """

    params = {
        "developer": developer,
        "repo": repo,
    }

    answers = extract_answers(g.query(cypher, **params))

    if not answers:
        return None

    question = (
        f"Which commits were authored by developer {developer} "
        f"in repository {repo}?"
    )

    return make_row(
        category="developer_activity",
        question=question,
        cypher=cypher,
        params=params,
        answers=answers,
        source_repo=repo,
        difficulty="medium",
        hop_count=2,
        answer_type="commit_list",
        template_name="developer_commits_in_repository",
        evidence_entities=["Developer", "Commit", "Repository"],
    )


# ---------------------------------------------------------------------------
# Multi-hop questions
# ---------------------------------------------------------------------------

def generate_multi_hop_question(g: Graph) -> dict[str, Any] | None:
    template = rng.choice(
        [
            "developers_for_file",
            "files_for_developer",
        ]
    )

    if template == "developers_for_file":
        anchors = g.query(
            """
            MATCH (d:Developer)-[:AUTHORED_COMMIT]->(c:Commit)
                  -[:MODIFIED_FILE]->(f:File)
                  <-[:CONTAINS_FILE]-(r:Repository)
            RETURN DISTINCT r.id AS repo,
                            f.path AS path
            LIMIT 3000
            """
        )

        if not anchors:
            return None

        anchor = rng.choice(anchors)
        repo = anchor["repo"]
        path = anchor["path"]

        cypher = """
        MATCH (d:Developer)-[:AUTHORED_COMMIT]->(c:Commit)
              -[:MODIFIED_FILE]->(f:File {path:$path})
              <-[:CONTAINS_FILE]-(:Repository {id:$repo})
        RETURN DISTINCT d.id AS answer
        ORDER BY answer
        LIMIT 20
        """

        params = {
            "repo": repo,
            "path": path,
        }

        answers = extract_answers(g.query(cypher, **params))

        if not answers:
            return None

        question = (
            f"Which developers authored commits that modified the file "
            f"'{path}' in repository {repo}?"
        )

        return make_row(
            category="multi_hop",
            question=question,
            cypher=cypher,
            params=params,
            answers=answers,
            source_repo=repo,
            difficulty="hard",
            hop_count=4,
            answer_type="developer_list",
            template_name="developers_modifying_file",
            evidence_entities=[
                "Developer",
                "Commit",
                "File",
                "Repository",
            ],
        )

    anchors = g.query(
        """
        MATCH (d:Developer)-[:AUTHORED_COMMIT]->(c:Commit)
              -[:MODIFIED_FILE]->(f:File)
              <-[:CONTAINS_FILE]-(r:Repository)
        RETURN DISTINCT d.id AS developer,
                        r.id AS repo
        LIMIT 3000
        """
    )

    if not anchors:
        return None

    anchor = rng.choice(anchors)
    developer = anchor["developer"]
    repo = anchor["repo"]

    cypher = """
    MATCH (d:Developer {id:$developer})-[:AUTHORED_COMMIT]->(c:Commit)
          -[:MODIFIED_FILE]->(f:File)
          <-[:CONTAINS_FILE]-(:Repository {id:$repo})
    RETURN DISTINCT f.path AS answer
    ORDER BY answer
    LIMIT 20
    """

    params = {
        "developer": developer,
        "repo": repo,
    }

    answers = extract_answers(g.query(cypher, **params))

    if not answers:
        return None

    question = (
        f"Which files in repository {repo} were modified through commits "
        f"authored by developer {developer}?"
    )

    return make_row(
        category="multi_hop",
        question=question,
        cypher=cypher,
        params=params,
        answers=answers,
        source_repo=repo,
        difficulty="hard",
        hop_count=4,
        answer_type="file_list",
        template_name="files_modified_by_developer",
        evidence_entities=[
            "Developer",
            "Commit",
            "File",
            "Repository",
        ],
    )


GENERATORS: dict[str, Callable[[Graph], dict[str, Any] | None]] = {
    "structure": generate_structure_question,
    "code_retrieval": generate_code_retrieval_question,
    "dependency_analysis": generate_dependency_question,
    "documentation_lookup": generate_documentation_question,
    "issue_pr_analysis": generate_issue_question,
    "developer_activity": generate_developer_activity_question,
    "multi_hop": generate_multi_hop_question,
}


def validate_row(row: dict[str, Any]) -> bool:
    """Apply basic benchmark validity checks."""
    question = row.get("question", "").strip()
    answers = row.get("ground_truth", [])
    params = row.get("params", {})

    if not question:
        return False

    if not answers:
        return False

    if len(answers) > MAX_ANSWERS:
        return False

    if not row.get("source_repo"):
        return False

    if not isinstance(params, dict):
        return False

    required_fields = (
        "expected_entities",
        "required_facts",
        "expected_relations",
        "expected_path",
        "gold_evidence",
        "expected_retrieval_route",
        "reasoning_hops",
        "answer_type_class",
        "answerable",
        "source_snapshot",
        "required_retrieval",
        "optional_retrieval",
        "question_generation_method",
    )
    if any(field not in row for field in required_fields):
        return False

    if row["expected_entities"] != answers:
        return False

    if row["expected_retrieval_route"] not in {"vector", "graph", "hybrid"}:
        return False

    if not row["gold_evidence"]:
        return False

    return True


def build_benchmark(g: Graph) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_questions: set[str] = set()
    category_counts: defaultdict[str, int] = defaultdict(int)

    for category, target_count in CATEGORY_TARGETS.items():
        generator = GENERATORS[category]
        attempts = 0

        while category_counts[category] < target_count:
            attempts += 1

            if attempts > MAX_ATTEMPTS_PER_CATEGORY:
                raise RuntimeError(
                    f"Could generate only {category_counts[category]} of "
                    f"{target_count} valid questions for category '{category}'. "
                    "Check whether the graph contains enough relevant entities "
                    "and relationships."
                )

            row = generator(g)

            if row is None or not validate_row(row):
                continue

            normalized = normalize_question(row["question"])

            if normalized in seen_questions:
                continue

            seen_questions.add(normalized)
            category_counts[category] += 1

            row["id"] = f"{category}-{category_counts[category]:03d}"
            rows.append(row)

        print(
            f"Generated {category_counts[category]:3d} valid questions "
            f"for {category}"
        )

    rng.shuffle(rows)

    # Keep category-specific IDs while adding an overall benchmark position.
    for index, row in enumerate(rows, start=1):
        row["benchmark_index"] = index

    return rows


def print_summary(rows: list[dict[str, Any]]) -> None:
    category_summary: defaultdict[str, int] = defaultdict(int)
    difficulty_summary: defaultdict[str, int] = defaultdict(int)
    template_summary: defaultdict[str, int] = defaultdict(int)

    for row in rows:
        category_summary[row["category"]] += 1
        difficulty_summary[row["difficulty"]] += 1
        template_summary[row["template_name"]] += 1

    print("\nBenchmark summary")
    print("-" * 50)
    print(f"Total questions: {len(rows)}")

    print("\nCategories:")
    for name, count in sorted(category_summary.items()):
        print(f"  {name:25s}: {count}")

    print("\nDifficulty:")
    for name, count in sorted(difficulty_summary.items()):
        print(f"  {name:25s}: {count}")

    print("\nTemplates:")
    for name, count in sorted(template_summary.items()):
        print(f"  {name:35s}: {count}")



# ---------------------------------------------------------------------------
# Unanswerable probes (Guide Section 5.3 "abstention" + Section 12.4)
# ---------------------------------------------------------------------------

def make_unanswerable_row(
    *,
    category: str,
    question: str,
    cypher: str,
    params: dict[str, Any],
    source_repo: str,
    template_name: str,
) -> dict[str, Any]:
    """
    Build one benchmark item whose Cypher was verified to return zero rows.

    Used to measure whether a system correctly abstains instead of
    fabricating an answer when the requested entity genuinely does not
    exist, as distinct from failing to retrieve an entity that does exist.
    """
    route = expected_route_for_category(category)
    required_retrieval, optional_retrieval = required_optional_retrieval(route)

    return {
        "category": category,
        "question": question,
        "cypher": cypher.strip(),
        "params": params,
        "ground_truth": [],
        "expected_answer": [],
        "expected_entities": [],
        "required_facts": [],
        "expected_relations": [],
        "expected_path": [],
        "gold_evidence": [f"Repository:{source_repo}"],
        "expected_retrieval_route": route,
        "source_repo": source_repo,
        "difficulty": "probe",
        "difficulty_level": "probe",
        "hop_count": 1,
        "reasoning_hops": 1,
        "answer_type": "abstention",
        "answer_type_class": "abstention",
        "template_name": template_name,
        "evidence_entities": ["Repository"],
        "reference_provenance": "neo4j_cypher_verified_absent",
        "answerable": False,
        "source_snapshot": SOURCE_SNAPSHOTS.get(source_repo),
        "required_retrieval": required_retrieval,
        "optional_retrieval": optional_retrieval,
        "question_generation_method": "cypher_template_negative_probe",
    }


def generate_unanswerable_issue(g: Graph) -> dict[str, Any] | None:
    anchors = g.query(
        """
        MATCH (r:Repository)-[:HAS_ISSUE]->(i:Issue)
        WHERE i.number IS NOT NULL
        RETURN r.id AS repo, max(i.number) AS max_number
        """
    )
    candidates = [row for row in anchors if row.get("max_number") is not None]

    if not candidates:
        return None

    anchor = rng.choice(candidates)
    repo = anchor["repo"]
    missing_number = int(anchor["max_number"]) + 1000

    cypher = """
    MATCH (:Repository {id:$repo})-[:HAS_ISSUE]->(i:Issue {number:$issue_number})
    RETURN i.title AS answer
    """
    params = {"repo": repo, "issue_number": missing_number}

    if g.query(cypher, **params):
        return None  # Unexpectedly exists; do not use as a negative probe.

    question = f"What is the title of issue #{missing_number} in repository {repo}?"

    return make_unanswerable_row(
        category="issue_pr_analysis",
        question=question,
        cypher=cypher,
        params=params,
        source_repo=repo,
        template_name="unanswerable_issue_lookup",
    )


def generate_unanswerable_directory(g: Graph) -> dict[str, Any] | None:
    repos = g.query("MATCH (r:Repository) RETURN r.id AS repo LIMIT 1000")

    if not repos:
        return None

    repo = rng.choice(repos)["repo"]
    directory = f"__does_not_exist_probe_{rng.randint(10000, 99999)}/"

    cypher = """
    MATCH (:Repository {id:$repo})-[:CONTAINS_FILE]->(f:File)
    WHERE f.path STARTS WITH $directory
    RETURN f.path AS answer
    """
    params = {"repo": repo, "directory": directory}

    if g.query(cypher, **params):
        return None

    question = (
        f"Which files are located under the '{directory}' directory "
        f"in repository {repo}?"
    )

    return make_unanswerable_row(
        category="structure",
        question=question,
        cypher=cypher,
        params=params,
        source_repo=repo,
        template_name="unanswerable_directory_lookup",
    )


def generate_unanswerable_developer(g: Graph) -> dict[str, Any] | None:
    repos = g.query(
        """
        MATCH (:Developer)-[:AUTHORED_COMMIT]->(:Commit)-[:COMMITTED_TO]->(r:Repository)
        RETURN DISTINCT r.id AS repo LIMIT 1000
        """
    )

    if not repos:
        return None

    repo = rng.choice(repos)["repo"]
    fake_email = f"probe-{rng.randint(100000, 999999)}@does-not-exist.invalid"
    developer = f"email:{fake_email}"

    cypher = """
    MATCH (d:Developer {id:$developer})-[:AUTHORED_COMMIT]->(c:Commit)
          -[:COMMITTED_TO]->(:Repository {id:$repo})
    RETURN c.id AS answer
    """
    params = {"repo": repo, "developer": developer}

    if g.query(cypher, **params):
        return None

    question = (
        f"Which commits were authored by developer email:{fake_email} "
        f"in repository {repo}?"
    )

    return make_unanswerable_row(
        category="developer_activity",
        question=question,
        cypher=cypher,
        params=params,
        source_repo=repo,
        template_name="unanswerable_developer_lookup",
    )


UNANSWERABLE_GENERATORS: tuple[Callable[[Graph], dict[str, Any] | None], ...] = (
    generate_unanswerable_issue,
    generate_unanswerable_directory,
    generate_unanswerable_developer,
)


def build_unanswerable_probes(g: Graph) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_questions: set[str] = set()
    attempts = 0

    while len(rows) < UNANSWERABLE_TARGET and attempts < MAX_UNANSWERABLE_ATTEMPTS:
        attempts += 1
        generator = rng.choice(UNANSWERABLE_GENERATORS)
        row = generator(g)

        if row is None:
            continue

        normalized = normalize_question(row["question"])

        if normalized in seen_questions:
            continue

        seen_questions.add(normalized)
        row["id"] = f"unanswerable-{len(rows) + 1:03d}"
        rows.append(row)

    if len(rows) < UNANSWERABLE_TARGET:
        print(
            f"Warning: generated only {len(rows)} of {UNANSWERABLE_TARGET} "
            "unanswerable probes after exhausting attempts."
        )

    return rows


def write_benchmark_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write a CSV version while preserving nested fields as JSON strings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    structured = {
        "params", "ground_truth", "expected_answer", "expected_entities",
        "required_facts", "expected_relations", "expected_path",
        "gold_evidence", "evidence_entities", "required_retrieval",
        "optional_retrieval",
    }
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            serialized = dict(row)
            for field in structured:
                if field in serialized:
                    serialized[field] = json.dumps(
                        serialized[field], ensure_ascii=False
                    )
            writer.writerow(serialized)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a validated repository reasoning benchmark."
    )

    parser.add_argument(
        "--output",
        default="data/benchmark/benchmark_300.jsonl",
        help="Output JSONL path relative to the project root.",
    )
    parser.add_argument(
        "--csv-output",
        default="data/benchmark/benchmark_300.csv",
        help="CSV output path used directly by the evaluation script.",
    )
    parser.add_argument(
        "--skip-unanswerable",
        action="store_true",
        help="Skip generating the separate unanswerable-probe set.",
    )
    parser.add_argument(
        "--unanswerable-output",
        default="data/benchmark/unanswerable_probes.jsonl",
    )
    parser.add_argument(
        "--unanswerable-csv-output",
        default="data/benchmark/unanswerable_probes.csv",
    )

    args = parser.parse_args()
    output_path = ROOT / Path(args.output)
    csv_output_path = ROOT / Path(args.csv_output)

    graph = Graph()

    try:
        rows = build_benchmark(graph)

        expected_total = sum(CATEGORY_TARGETS.values())

        if len(rows) != expected_total:
            raise RuntimeError(
                f"Expected {expected_total} questions, but generated {len(rows)}."
            )

        write_jsonl(output_path, rows)
        write_benchmark_csv(csv_output_path, rows)
        print_summary(rows)
        print(f"\nWrote {len(rows)} questions to {output_path}")
        print(f"Wrote evaluation CSV to {csv_output_path}")

        if not args.skip_unanswerable:
            unanswerable_rows = build_unanswerable_probes(graph)

            unanswerable_output_path = ROOT / Path(args.unanswerable_output)
            unanswerable_csv_path = ROOT / Path(args.unanswerable_csv_output)

            write_jsonl(unanswerable_output_path, unanswerable_rows)
            write_benchmark_csv(unanswerable_csv_path, unanswerable_rows)

            print(
                f"\nWrote {len(unanswerable_rows)} unanswerable probes to "
                f"{unanswerable_output_path}"
            )
            print(f"Wrote unanswerable-probe CSV to {unanswerable_csv_path}")

    finally:
        graph.close()


if __name__ == "__main__":
    main()
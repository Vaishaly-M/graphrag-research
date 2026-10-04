
from __future__ import annotations

import argparse
import os
import random
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from faker import Faker

from src.common import ROOT, ensure_dirs, retry, write_jsonl


fake = Faker()
random.seed(42)
Faker.seed(42)


def get_ollama_base_url() -> str:
    """Return the Ollama base URL without a trailing slash."""

    return os.getenv(
        "OLLAMA_URL",
        "http://localhost:11434",
    ).rstrip("/")


def get_ollama_model() -> str:
    """Return the configured Ollama model name."""

    return os.getenv(
        "OLLAMA_MODEL",
        "llama3.1:8b",
    ).strip()


def get_installed_models() -> list[str]:
    """Return model names currently installed in Ollama."""

    url = f"{get_ollama_base_url()}/api/tags"

    try:
        response = requests.get(
            url,
            timeout=15,
        )
        response.raise_for_status()
    except requests.ConnectionError as error:
        raise RuntimeError(
            "Cannot connect to Ollama.\n"
            "Make sure the Ollama application is running.\n"
            f"Expected server: {get_ollama_base_url()}"
        ) from error
    except requests.RequestException as error:
        raise RuntimeError(
            f"Failed to query Ollama models: {error}"
        ) from error

    payload = response.json()

    installed_models: list[str] = []

    for item in payload.get("models", []):
        model_name = item.get("name") or item.get("model")

        if model_name:
            installed_models.append(str(model_name))

    return installed_models


def validate_ollama() -> None:
    """Confirm that Ollama is running and the configured model exists."""

    model = get_ollama_model()
    installed_models = get_installed_models()

    if not installed_models:
        raise RuntimeError(
            "Ollama is running, but no models are installed.\n"
            f"Install the required model with:\n"
            f"ollama pull {model}"
        )

    exact_match = model in installed_models

    base_name_match = any(
        installed.split(":")[0] == model.split(":")[0]
        for installed in installed_models
    )

    if not exact_match and not base_name_match:
        installed_text = "\n".join(
            f"  - {name}"
            for name in installed_models
        )

        raise RuntimeError(
            f"Ollama model '{model}' is not installed.\n\n"
            f"Installed models:\n{installed_text}\n\n"
            f"Install the required model using:\n"
            f"ollama pull {model}\n\n"
            "Alternatively, change OLLAMA_MODEL in your .env file "
            "to one of the installed model names."
        )

    print(
        f"Ollama connection successful. Using model: {model}",
        flush=True,
    )


def generate_with_ollama(prompt: str) -> str:
    """Generate one text response using the local Ollama API."""

    base_url = get_ollama_base_url()
    model = get_ollama_model()
    url = f"{base_url}/api/generate"

    def call() -> str:
        try:
            response = requests.post(
                url,
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.4,
                        "seed": 42,
                    },
                },
                timeout=300,
            )

            if response.status_code == 404:
                try:
                    error_message = response.json().get(
                        "error",
                        response.text,
                    )
                except ValueError:
                    error_message = response.text

                raise RuntimeError(
                    f"Ollama returned 404: {error_message}\n"
                    f"The configured model is '{model}'.\n"
                    f"Run: ollama pull {model}"
                )

            response.raise_for_status()

            payload = response.json()
            generated_text = payload.get(
                "response",
                "",
            ).strip()

            return generated_text

        except requests.ConnectionError as error:
            raise RuntimeError(
                "Could not connect to Ollama at "
                f"{base_url}.\n"
                "Start the Ollama application and try again."
            ) from error

        except requests.Timeout as error:
            raise RuntimeError(
                f"Ollama timed out while using model '{model}'."
            ) from error

        except requests.RequestException as error:
            raise RuntimeError(
                f"Ollama request failed: {error}"
            ) from error

    text = retry(call)

    if not text:
        raise ValueError(
            "Ollama returned an empty response."
        )

    invalid_starts = (
        "error",
        "sorry",
        "i cannot",
        "i can't",
    )

    if text.lower().startswith(invalid_starts):
        raise ValueError(
            f"Invalid Ollama output: {text}"
        )

    return text


def generate_commit_message(
    action: str,
    file_path: str,
    use_ollama: bool,
) -> str:
    """Create a commit message."""

    fallback_message = f"{action} {file_path}"

    if not use_ollama:
        return fallback_message

    prompt = (
        "Write exactly one concise software commit message.\n"
        f"Action: {action}\n"
        f"File: {file_path}\n"
        "Use imperative style.\n"
        "Do not use quotation marks.\n"
        "Do not include explanations."
    )

    return generate_with_ollama(prompt)


def generate_issue_body(
    file_path: str,
    use_ollama: bool,
) -> str:
    """Create a short issue description."""

    fallback_body = (
        f"A reproducible failure occurs in {file_path}. "
        "The component should be investigated and corrected."
    )

    if not use_ollama:
        return fallback_body

    prompt = (
        "Write a realistic two-sentence software bug report.\n"
        f"Affected file: {file_path}\n"
        "Sentence one must describe the observed problem.\n"
        "Sentence two must describe the expected behavior.\n"
        "Output only the report."
    )

    return generate_with_ollama(prompt)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic repository data."
    )

    parser.add_argument(
        "--commits",
        type=int,
        default=300,
        help="Number of synthetic commits.",
    )

    parser.add_argument(
        "--issues",
        type=int,
        default=120,
        help="Number of synthetic issues.",
    )

    parser.add_argument(
        "--prs",
        type=int,
        default=80,
        help="Number of synthetic pull requests.",
    )

    parser.add_argument(
        "--no-ollama",
        action="store_true",
        help="Generate template-based text without using Ollama.",
    )

    args = parser.parse_args()

    ensure_dirs()
    load_dotenv(ROOT / ".env")

    use_ollama = not args.no_ollama

    if use_ollama:
        validate_ollama()
    else:
        print(
            "Ollama disabled. Using deterministic template text.",
            flush=True,
        )

    repository_slug = "synthetic-org/platform"

    projects = [
        {
            "id": f"project-{index}",
            "name": f"Project-{index}",
        }
        for index in range(1, 6)
    ]

    developers = [
        {
            "id": f"dev-{index}",
            "name": fake.name(),
            "email": fake.email(),
        }
        for index in range(1, 21)
    ]

    files = [
        {
            "id": f"synthetic:file-{index}",
            "repo": repository_slug,
            "path": (
                f"src/component_{index % 15}/"
                f"module_{index}.py"
            ),
            "extension": ".py",
            "content": (
                f"def function_{index}():\n"
                f"    return {index}\n"
            ),
            "project_id": projects[index % len(projects)]["id"],
        }
        for index in range(100)
    ]

    commits: list[dict[str, Any]] = []

    print(
        f"Generating {args.commits} commits...",
        flush=True,
    )

    for index in range(args.commits):
        developer = random.choice(developers)
        file_record = random.choice(files)
        action = random.choice(
            [
                "fix",
                "add",
                "refactor",
                "test",
            ]
        )

        message = generate_commit_message(
            action=action,
            file_path=file_record["path"],
            use_ollama=use_ollama,
        )

        commits.append(
            {
                "id": f"syn-c-{index}",
                "repo": repository_slug,
                "message": message,
                "timestamp": fake.date_time_between(
                    start_date="-2y",
                    end_date="now",
                ).isoformat(),
                "author_id": developer["id"],
                "author_name": developer["name"],
                "author_email": developer["email"],
                "modified_files": [
                    {
                        "path": file_record["path"],
                        "added": random.randint(1, 50),
                        "deleted": random.randint(0, 20),
                    }
                ],
            }
        )

        if (index + 1) % 10 == 0:
            print(
                f"Generated commits: {index + 1}/{args.commits}",
                flush=True,
            )

    issues: list[dict[str, Any]] = []

    print(
        f"Generating {args.issues} issues...",
        flush=True,
    )

    for index in range(args.issues):
        file_record = random.choice(files)
        author = random.choice(developers)
        assignee = random.choice(developers)

        issue_body = generate_issue_body(
            file_path=file_record["path"],
            use_ollama=use_ollama,
        )

        issues.append(
            {
                "id": f"syn-issue-{index}",
                "repo": repository_slug,
                "number": index + 1,
                "title": f"Issue in {file_record['path']}",
                "body": issue_body,
                "state": random.choice(
                    [
                        "open",
                        "closed",
                    ]
                ),
                "author": author["email"],
                "author_id": author["id"],
                "assignees": [assignee["email"]],
                "assignee_ids": [assignee["id"]],
                "labels": ["bug"],
                "affected_file": file_record["path"],
            }
        )

        if (index + 1) % 10 == 0:
            print(
                f"Generated issues: {index + 1}/{args.issues}",
                flush=True,
            )

    pull_requests: list[dict[str, Any]] = []

    print(
        f"Generating {args.prs} pull requests...",
        flush=True,
    )

    for index in range(args.prs):
        developer = random.choice(developers)
        linked_commit = random.choice(commits)
        component_number = index % 15

        pull_requests.append(
            {
                "id": f"syn-pr-{index}",
                "repo": repository_slug,
                "number": index + 1,
                "title": (
                    f"Improve component {component_number}"
                ),
                "body": (
                    f"Updates component {component_number} "
                    "and resolves the associated implementation issue."
                ),
                "state": "closed",
                "author": developer["email"],
                "author_id": developer["id"],
                "merged": True,
                "merge_commit_sha": linked_commit["id"],
            }
        )

    output_directory = ROOT / "data" / "synthetic"
    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_jsonl(
        output_directory / "projects.jsonl",
        projects,
    )

    write_jsonl(
        output_directory / "developers.jsonl",
        developers,
    )

    write_jsonl(
        output_directory / "files.jsonl",
        files,
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

    print("\nSynthetic generation completed.", flush=True)
    print(f"Projects: {len(projects)}", flush=True)
    print(f"Developers: {len(developers)}", flush=True)
    print(f"Files: {len(files)}", flush=True)
    print(f"Commits: {len(commits)}", flush=True)
    print(f"Issues: {len(issues)}", flush=True)
    print(
        f"Pull requests: {len(pull_requests)}",
        flush=True,
    )
    print(f"Output: {output_directory}", flush=True)


if __name__ == "__main__":
    main()

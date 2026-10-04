"""Prepare a frozen eight-system experiment without making service calls."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEMS = (
    "plain_llm", "vector_rag", "langchain_graphrag", "llamaindex_graphrag",
    "fixed_graph_rag", "fixed_hybrid_rag", "oracle_hybrid_rag",
    "adaptive_hybrid_graphrag",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def validate_questions(rows):
    ids = [row["id"] for row in rows]
    if len(ids) != 242 or len(set(ids)) != 242:
        raise ValueError("Expected exactly 242 unique hidden-test IDs")
    if any(not row["question"].strip() for row in rows):
        raise ValueError("Empty hidden-test question")


def verify(output):
    manifest = json.loads((output / "manifest.json").read_text())
    for name, expected in manifest["sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Frozen artifact changed: {name}; use a new output root")
    print("Frozen source, configuration, and input fingerprints verified")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path("results/routing_evaluation_v1"))
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    output = (ROOT / args.output_root).resolve()
    output.relative_to(ROOT)  # keep generated artifacts inside this workspace
    if args.verify:
        verify(output)
        return
    if args.repeats < 1:
        raise ValueError("repeats must be positive")
    source = ROOT / "data/benchmark/splits/hidden_test_questions.csv"
    rows = read_csv(source)
    validate_questions(rows)
    if any(row.get("expected_retrieval_route") not in {"graph", "vector", "hybrid"} for row in rows):
        raise ValueError("Oracle input requires a valid route for every question")
    output.mkdir(parents=True, exist_ok=False)
    for filename, fields in (
        ("questions.csv", ["id", "question"]),
        ("oracle_questions.csv", ["id", "question", "expected_retrieval_route"]),
    ):
        with (output / filename).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    order = list(SYSTEMS)
    random.Random(args.seed).shuffle(order)
    tracked = [source, ROOT / "config/experiment.yaml", ROOT / "docs/adaptive_routing_protocol.md"]
    tracked += sorted((ROOT / "src").rglob("*.py"))
    tracked += [Path(__file__).resolve(), output / "questions.csv", output / "oracle_questions.csv"]
    manifest = {
        "questions": 242, "systems": order, "repeats": args.repeats,
        "seed": args.seed, "primary_metric": "answer_accuracy",
        "status": "prepared_not_executed", "test_set_reused": True,
        "sha256": {str(p.relative_to(ROOT)): digest(p) for p in tracked},
        "limitations": ["Model, dependencies, graph and index must also be frozen and recorded before execution.",
                        "System-block randomization does not eliminate service-time confounding."],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    def quote(path):
        return "'" + str(path).replace("'", "''") + "'"
    def command(parts):
        return " ".join(parts) + '\nif ($LASTEXITCODE -ne 0) { throw "Experiment step failed" }\n'
    script = "$ErrorActionPreference = 'Stop'\nSet-Location " + quote(ROOT) + "\n"
    script += command(["python -m scripts.prepare_routing_evaluation --verify --output-root", quote(output)])
    script += command(["python -m scripts.record_environment"])
    for system in order:
        benchmark = output / ("oracle_questions.csv" if system == "oracle_hybrid_rag" else "questions.csv")
        script += command(["python -m src.systems." + system, "--benchmark-file", quote(benchmark),
                           "--output-dir", quote(output / "raw"), "--repeats", str(args.repeats)])
    script += command(["python -m src.evaluation.routing_diagnostics --results-dir", quote(output / "raw"),
                       "--output-dir", quote(output / "metrics"), "--repeats", str(args.repeats), "--require-no-errors"])
    script += command(["python -m src.evaluation.metrics --input-dir", quote(output / "raw"),
                       "--output-dir", quote(output / "metrics"),
                       "--benchmark-file data/benchmark/splits/hidden_test_answer_key.csv"])
    script += command(["python -m src.evaluation.statistics --input", quote(output / "metrics/per_question_metrics.csv"),
                       "--output-dir", quote(output / "metrics")])
    (output / "run.ps1").write_text(script, encoding="utf-8")
    print(f"Prepared {242 * 8 * args.repeats} outputs; no API calls made. Run: {output / 'run.ps1'}")


if __name__ == "__main__":
    main()

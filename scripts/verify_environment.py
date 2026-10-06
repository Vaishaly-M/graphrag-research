"""Read-only runtime preflight; never prints credentials."""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import ROOT
from src.evaluation.reproducibility import sha256


def verify():
    report = {}
    report["gemini"] = dict(key_present=bool(os.getenv("GEMINI_API_KEY")),
                            model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview"),
                            remote_model_availability="not checked; key presence is not model access")
    try:
        from neo4j import GraphDatabase
        with GraphDatabase.driver(os.environ["NEO4J_URI"],
                auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
                connection_timeout=10, connection_acquisition_timeout=10,
                max_transaction_retry_time=0) as driver:
            driver.verify_connectivity()
            rows, _, _ = driver.execute_query("MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS n",
                database_=os.getenv("NEO4J_DATABASE", "neo4j"))
            report["neo4j"] = dict(status="ok", label_counts=[r.data() for r in rows])
    except Exception as exc:
        report["neo4j"] = dict(status="error", error_type=type(exc).__name__)
    directory = Path(os.getenv("VECTOR_INDEX_DIR", str(ROOT / "data/vector_index")))
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        good = all(sha256(directory / filename) == manifest[field] for filename, field in
                   [("index.faiss", "index_sha256"), ("docs.json", "docs_sha256")])
        report["vector_index"] = dict(status="ok" if good else "error", directory=str(directory),
                                      manifest=manifest, hashes_match=good)
    except Exception as exc:
        report["vector_index"] = dict(status="error", directory=str(directory), error_type=type(exc).__name__)
    try:
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        with urllib.request.urlopen(host + "/api/tags", timeout=5) as response:
            names = [m["name"] for m in json.load(response)["models"]]
        report["ollama"] = dict(status="ok", models=names,
                                qwen2_5_pulled=any(n.startswith("qwen2.5:") for n in names))
    except Exception as exc:
        report["ollama"] = dict(status="error", error_type=type(exc).__name__, qwen2_5_pulled=False)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="results/v2/environment.json")
    args = parser.parse_args()
    report = verify()
    output = ROOT / args.output
    if not output.resolve().is_relative_to((ROOT / "results/v2").resolve()):
        parser.error("output must be under results/v2")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, result in report.items():
        display = {k: v for k, v in result.items() if k != "manifest"}
        print(name + ": " + json.dumps(display))
    return int(not report["gemini"]["key_present"] or any(report[k].get("status") != "ok" for k in
               ["neo4j", "vector_index", "ollama"]) or not report["ollama"]["qwen2_5_pulled"])


if __name__ == "__main__":
    sys.exit(main())

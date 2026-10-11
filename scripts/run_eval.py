"""Single v2 entry point: python scripts/run_eval.py SYSTEM SPLIT --run-name NAME."""
import argparse
import importlib
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import ROOT
from src.evaluation.reproducibility import snapshot, save_snapshot, source_hashes, sha256


SYSTEMS = ("plain_llm", "vector_rag", "fixed_graph_rag", "fixed_hybrid_rag",
           "adaptive_hybrid_graphrag", "adaptive_hybrid_graphrag_v2", "oracle_hybrid_rag", "langchain_graphrag", "llamaindex_graphrag")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("system", choices=SYSTEMS)
    p.add_argument("split", choices=["development", "validation", "hidden-test", "human-test", "router-tuning"])
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--run-name", required=True)
    p.add_argument("--discard-first-run", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--no-cache", action="store_true")
    args = p.parse_args()
    if not args.run_name or Path(args.run_name).name != args.run_name or args.run_name in {".", ".."}:
        p.error("run-name must be a single directory name")
    if (ROOT / "results/v2/vector_index/manifest.json").exists():
        os.environ.setdefault("VECTOR_INDEX_DIR", str(ROOT / "results/v2/vector_index"))
    benchmark = ROOT / "data/benchmark/splits_v2" / (args.split + ".csv")
    manifest = json.loads((benchmark.parent / "manifest.json").read_text(encoding="utf-8"))
    if sha256(benchmark) != manifest["splits"][args.split]["sha256"]:
        raise RuntimeError("Frozen benchmark hash mismatch; reviewed re-freeze required")
    index_dir = Path(os.getenv("VECTOR_INDEX_DIR", str(ROOT / "data/vector_index")))
    index_manifest = index_dir / "manifest.json"
    if args.system != "plain_llm" and index_manifest.exists():
        if json.loads(index_manifest.read_text(encoding="utf-8")).get("diagnostic_only"):
            raise RuntimeError("Diagnostic legacy index is forbidden for evaluation; complete an explicit manifest-backed rebuild")
    output = ROOT / "results/v2" / args.run_name
    save_snapshot(output, snapshot(benchmark, args.system, repeats=args.repeats,
        discard_first_run=args.discard_first_run, cache_enabled=not args.no_cache,
        limit=None, source_hashes=source_hashes()))
    cls = importlib.import_module("src.systems." + args.system).System
    try:
        system = cls(benchmark_file=benchmark) if args.system == "oracle_hybrid_rag" else cls()
    except Exception as exc:
        (output / "setup_error.json").write_text(json.dumps({"error_type": type(exc).__name__}), encoding="utf-8")
        raise
    try:
        system.run(benchmark=benchmark, output_dir=output,
                   repeats=args.repeats, discard_first_run=args.discard_first_run, no_cache=args.no_cache)
    finally:
        if hasattr(system, "graph"):
            system.graph.close()


if __name__ == "__main__":
    main()

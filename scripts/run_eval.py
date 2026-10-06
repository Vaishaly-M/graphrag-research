"""Single v2 entry point: python scripts/run_eval.py SYSTEM SPLIT --run-name NAME."""
import argparse
import importlib
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import ROOT


SYSTEMS = ("plain_llm", "vector_rag", "fixed_graph_rag", "fixed_hybrid_rag",
           "adaptive_hybrid_graphrag", "oracle_hybrid_rag", "langchain_graphrag", "llamaindex_graphrag")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("system", choices=SYSTEMS)
    p.add_argument("split", choices=["development", "validation", "hidden-test", "human-test"])
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--run-name", required=True)
    p.add_argument("--discard-first-run", action="store_true")
    p.add_argument("--no-cache", action="store_true")
    args = p.parse_args()
    if not args.run_name or Path(args.run_name).name != args.run_name or args.run_name in {".", ".."}:
        p.error("run-name must be a single directory name")
    if (ROOT / "results/v2/vector_index/manifest.json").exists():
        os.environ.setdefault("VECTOR_INDEX_DIR", str(ROOT / "results/v2/vector_index"))
    benchmark = ROOT / "data/benchmark/splits_v2" / (args.split + ".csv")
    cls = importlib.import_module("src.systems." + args.system).System
    system = cls(benchmark_file=benchmark) if args.system == "oracle_hybrid_rag" else cls()
    try:
        system.run(benchmark=benchmark, output_dir=ROOT / "results/v2" / args.run_name,
                   repeats=args.repeats, discard_first_run=args.discard_first_run, no_cache=args.no_cache)
    finally:
        if hasattr(system, "graph"):
            system.graph.close()


if __name__ == "__main__":
    main()

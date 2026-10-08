"""Explicit v2 index build; never overwrite the legacy index by default."""
import argparse
import os
from pathlib import Path
from src.common import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="results/v2/vector_index")
    args = parser.parse_args()
    directory = (ROOT / args.output_dir).resolve()
    if not directory.is_relative_to((ROOT / "results/v2").resolve()):
        parser.error("new index output must be under results/v2")
    os.environ["VECTOR_INDEX_DIR"] = str(directory)
    from src.vector_store import VectorStore
    VectorStore().build()


if __name__ == "__main__":
    main()

"""
Scalability measurement with a realistic multi-entity subgraph (Guide
Section 18), not the original label-only isolated-node placeholder.

For each requested size N, builds a synthetic subgraph shaped like the
real schema -- Repository/Developer/Commit/File nodes connected by
CONTAINS_FILE/AUTHORED_COMMIT/COMMITTED_TO/MODIFIED_FILE relationships,
matching src/kg_construction/schema.cypher -- under a size-specific label
prefix so it never collides with real data. Runs 1-hop, 2-hop, 3-hop, and
an aggregation query 5 times after 1 warmup run and reports median and
IQR, per the README's own scalability guidance.

Also separately measures a local FAISS vector index at the same scale,
since vector and graph retrieval scale independently -- combining them
into one number would hide which one dominates a "hybrid" query's cost.
The vector measurement never touches Neo4j and is safe to run at any
size.

IMPORTANT (README Section 10): use a dedicated local Neo4j instance for
the graph portion at real scale, isolated from your benchmark database.
This script defaults to a small --sizes value specifically so it is safe
to run against a shared instance for a quick check; do not point large
sizes (the README's 10000-500000 range) at a shared Aura/production
instance.

Run:
    python -m src.scalability.generate_and_measure --sizes 1000,5000,10000
"""

from __future__ import annotations

import argparse
import os
import statistics
import time
from typing import Any

import numpy as np
import pandas as pd

from src.common import ROOT
from src.graph import Graph

WARMUP_RUNS = 1
MEASURED_RUNS = 5
EMBEDDING_DIMENSION = 384  # matches sentence-transformers/all-MiniLM-L6-v2


def label(prefix: str, suffix: str) -> str:
    return f"{prefix}{suffix}"


def cleanup(graph: Graph, prefix: str) -> None:
    for suffix in ("File", "Commit", "Developer", "Repository"):
        graph.execute(f"MATCH (n:{label(prefix, suffix)}) DETACH DELETE n")


def create_indexes(graph: Graph, prefix: str) -> None:
    """
    An unindexed property lookup at 100K+ scale measures index-miss cost,
    not the graph's real query complexity -- the production schema
    (schema.cypher) has id constraints on every node type, so this
    measurement should too.
    """
    for suffix in ("File", "Commit", "Developer", "Repository"):
        graph.execute(
            f"CREATE INDEX IF NOT EXISTS FOR (n:{label(prefix, suffix)}) "
            "ON (n.id)"
        )


def build_subgraph(graph: Graph, prefix: str, size: int) -> float:
    """
    Build one repository, `size` files, size//20 commits, size//200
    developers (each at least 1), each commit authored by one developer
    and modifying 3 files. Returns build time in seconds.
    """
    commit_count = max(1, size // 20)
    developer_count = max(1, size // 200)

    start = time.perf_counter()

    graph.execute(
        f"CREATE (:{label(prefix, 'Repository')} {{id: 0}})"
    )

    graph.execute(
        f"""
        UNWIND range(1, $developer_count) AS i
        CREATE (:{label(prefix, 'Developer')} {{id: i}})
        """,
        developer_count=developer_count,
    )

    graph.execute(
        f"""
        MATCH (r:{label(prefix, 'Repository')} {{id: 0}})
        UNWIND range(1, $size) AS i
        CREATE (f:{label(prefix, 'File')} {{id: i, bucket: i % 100}})
        MERGE (r)-[:CONTAINS_FILE]->(f)
        """,
        size=size,
    )

    graph.execute(
        f"""
        MATCH (r:{label(prefix, 'Repository')} {{id: 0}})
        UNWIND range(1, $commit_count) AS i
        CREATE (c:{label(prefix, 'Commit')} {{id: i}})
        MERGE (c)-[:COMMITTED_TO]->(r)
        WITH c, i
        MATCH (d:{label(prefix, 'Developer')} {{id: 1 + (i % $developer_count)}})
        MERGE (d)-[:AUTHORED_COMMIT]->(c)
        """,
        commit_count=commit_count,
        developer_count=developer_count,
    )

    graph.execute(
        f"""
        MATCH (c:{label(prefix, 'Commit')})
        UNWIND range(0, 2) AS offset
        WITH c, ((c.id * 3 + offset) % $size) + 1 AS file_id
        MATCH (f:{label(prefix, 'File')} {{id: file_id}})
        MERGE (c)-[:MODIFIED_FILE]->(f)
        """,
        size=size,
    )

    return time.perf_counter() - start


def repeated_query(
    graph: Graph, cypher: str, params: dict[str, Any]
) -> list[float]:
    latencies: list[float] = []

    for _ in range(WARMUP_RUNS + MEASURED_RUNS):
        start = time.perf_counter()
        graph.query(cypher, **params)
        latencies.append(time.perf_counter() - start)

    return latencies[WARMUP_RUNS:]


def iqr(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0

    quantiles = statistics.quantiles(values, n=4, method="inclusive")
    return quantiles[2] - quantiles[0]


def measure_graph_scalability(graph: Graph, size: int) -> dict[str, Any]:
    prefix = f"Scale{size}_"

    cleanup(graph, prefix)
    create_indexes(graph, prefix)
    build_time = build_subgraph(graph, prefix, size)

    developer_count = max(1, size // 200)

    one_hop = repeated_query(
        graph,
        f"""
        MATCH (:{label(prefix, 'Repository')} {{id:0}})
              -[:CONTAINS_FILE]->(f:{label(prefix, 'File')})
        WHERE f.bucket = 42
        RETURN count(f) AS count
        """,
        {},
    )

    two_hop = repeated_query(
        graph,
        f"""
        MATCH (d:{label(prefix, 'Developer')} {{id:$dev_id}})
              -[:AUTHORED_COMMIT]->(c:{label(prefix, 'Commit')})
              -[:COMMITTED_TO]->(:{label(prefix, 'Repository')} {{id:0}})
        RETURN count(c) AS count
        """,
        {"dev_id": 1 + (size % developer_count)},
    )

    three_hop = repeated_query(
        graph,
        f"""
        MATCH (d:{label(prefix, 'Developer')} {{id:$dev_id}})
              -[:AUTHORED_COMMIT]->(:{label(prefix, 'Commit')})
              -[:MODIFIED_FILE]->(f:{label(prefix, 'File')})
              <-[:CONTAINS_FILE]-(:{label(prefix, 'Repository')} {{id:0}})
        RETURN DISTINCT f.id AS id LIMIT 100
        """,
        {"dev_id": 1 + (size % developer_count)},
    )

    aggregation = repeated_query(
        graph,
        f"""
        MATCH (d:{label(prefix, 'Developer')})
              -[:AUTHORED_COMMIT]->(c:{label(prefix, 'Commit')})
              -[:COMMITTED_TO]->(:{label(prefix, 'Repository')} {{id:0}})
        WITH d, count(c) AS commit_count
        RETURN d.id AS id, commit_count
        ORDER BY commit_count DESC LIMIT 10
        """,
        {},
    )

    cleanup(graph, prefix)

    return {
        "nodes": size,
        "commits": max(1, size // 20),
        "developers": developer_count,
        "graph_build_time_s": build_time,
        "one_hop_median_s": statistics.median(one_hop),
        "one_hop_iqr_s": iqr(one_hop),
        "two_hop_median_s": statistics.median(two_hop),
        "two_hop_iqr_s": iqr(two_hop),
        "three_hop_median_s": statistics.median(three_hop),
        "three_hop_iqr_s": iqr(three_hop),
        "aggregation_median_s": statistics.median(aggregation),
        "aggregation_iqr_s": iqr(aggregation),
    }


def measure_vector_scalability(size: int, seed: int = 42) -> dict[str, Any]:
    import faiss

    rng = np.random.default_rng(seed)
    vectors = rng.random((size, EMBEDDING_DIMENSION), dtype="float32")
    faiss.normalize_L2(vectors)

    start = time.perf_counter()
    index = faiss.IndexFlatIP(EMBEDDING_DIMENSION)
    index.add(vectors)
    build_time = time.perf_counter() - start

    query = rng.random((1, EMBEDDING_DIMENSION), dtype="float32")
    faiss.normalize_L2(query)

    latencies: list[float] = []
    for _ in range(WARMUP_RUNS + MEASURED_RUNS):
        start = time.perf_counter()
        index.search(query, 10)
        latencies.append(time.perf_counter() - start)

    measured = latencies[WARMUP_RUNS:]

    return {
        "vector_build_time_s": build_time,
        "vector_query_median_s": statistics.median(measured),
        "vector_query_iqr_s": iqr(measured),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure graph and vector retrieval scalability."
    )
    parser.add_argument(
        "--sizes",
        default="1000,5000,10000",
        help=(
            "Comma-separated node counts. Keep these small for a shared "
            "instance; use a dedicated local Neo4j for the README's "
            "10000-500000 range."
        ),
    )
    parser.add_argument(
        "--skip-graph",
        action="store_true",
        help="Only measure vector scalability (safe on any machine).",
    )
    parser.add_argument(
        "--allow-remote-graph",
        action="store_true",
        help=(
            "Permit graph writes to a remote Neo4j instance. Only use this "
            "for a dedicated, disposable scalability database."
        ),
    )
    args = parser.parse_args()

    sizes = [int(size) for size in args.sizes.split(",")]
    rows: list[dict[str, Any]] = []

    uri = os.getenv("NEO4J_URI", "").lower()
    remote_uri = uri.startswith(("neo4j+s://", "neo4j+ssc://", "bolt+s://", "bolt+ssc://"))
    if not args.skip_graph and remote_uri and not args.allow_remote_graph:
        raise RuntimeError(
            "Refusing graph scalability writes to a remote Neo4j URI. "
            "Use a dedicated local database, or explicitly pass "
            "--allow-remote-graph only for a disposable remote instance."
        )

    graph = None if args.skip_graph else Graph()

    try:
        for size in sizes:
            row: dict[str, Any] = {}

            if graph is not None:
                row.update(measure_graph_scalability(graph, size))
            else:
                row["nodes"] = size

            row.update(measure_vector_scalability(size))

            print(row)
            rows.append(row)

        output_path = ROOT / "results" / "scalability.csv"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(output_path, index=False)
        print(f"\nWrote scalability results to: {output_path}")

    finally:
        if graph is not None:
            graph.close()


if __name__ == "__main__":
    main()

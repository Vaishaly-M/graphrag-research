"""Generate a fresh graph-verified tuning set; never repartition old questions."""
import hashlib
import json
import random
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import ROOT
from src.graph import Graph
from src.benchmark_gen import generate_benchmark as generation
from src.evaluation.reproducibility import read_csv, write_csv, sha256, snapshot, save_snapshot
from src.evaluation.metrics_v2 import items, gold_completeness


class RepositoryCandidates:
    """Scope candidate discovery before LIMIT; reference queries stay unchanged."""
    def __init__(self, graph, repository):
        self.graph, self.repository = graph, repository
        self.cache = {}

    def query(self, query, **params):
        if not params and "(r:Repository)" in query:
            scoped = query.replace("(r:Repository)", "(r:Repository {id:$tuning_repo})")
            if scoped not in self.cache:
                self.cache[scoped] = self.graph.query(scoped, tuning_repo=self.repository)
            return self.cache[scoped]
        return self.graph.query(query, **params)


def prepare():
    policy = json.loads((ROOT/"docs/phase2_selection_rule.json").read_text())
    directory = ROOT/"data/benchmark/splits_v2"
    target = directory/"router-tuning.csv"
    if target.exists():
        raise RuntimeError("Router tuning split already exists; never silently regenerate frozen data")
    excluded_questions, excluded_entities = set(), set()
    for name in policy["excluded_splits"]:
        for row in read_csv(directory/(name+".csv")):
            excluded_questions.add(generation.normalize_question(row["question"]))
            entity_set = tuple(sorted(items(row.get("expected_entities"))))
            if entity_set:
                excluded_entities.add(entity_set)
    generation.rng = random.Random(policy["seed"])
    graph = Graph()
    rows, seen, entity_sets = [], set(excluded_questions), set(excluded_entities)
    try:
        counts = graph.query("MATCH (n) RETURN count(n) AS n")
        if not counts or counts[0]["n"] == 0:
            raise RuntimeError("The configured graph is empty; cannot generate verified questions")
        repositories = graph.query("MATCH (r:Repository) WHERE r.id <> 'apache/airflow' RETURN r.id AS id ORDER BY id")
        candidates = [RepositoryCandidates(graph, r["id"]) for r in repositories]
        if not candidates:
            raise RuntimeError("No eligible tuning repositories")
        for category, generator in generation.GENERATORS.items():
            accepted = 0
            for _ in range(1000):
                candidate = generator(generation.rng.choice(candidates))
                if candidate is None or not generation.validate_row(candidate):
                    continue
                if candidate["source_repo"] == "apache/airflow":
                    continue
                question = generation.normalize_question(candidate["question"])
                entities = tuple(sorted(candidate["expected_entities"]))
                if question in seen or entities in entity_sets:
                    continue
                seen.add(question)
                entity_sets.add(entities)
                identifier = "router-tuning-"+hashlib.sha256(question.encode()).hexdigest()[:16]
                candidate.update(id=identifier, question_id=identifier, generation_seed=policy["seed"])
                complete, reason = gold_completeness(candidate)
                candidate.update(gold_complete=complete, gold_complete_reason=reason)
                rows.append(candidate)
                accepted += 1
                print(category, accepted, flush=True)
                if accepted == policy["questions_per_category"]:
                    break
            if accepted != policy["questions_per_category"]:
                raise RuntimeError(f"Insufficient disjoint examples for {category}: {accepted}; no split frozen")
        records = graph.query("MATCH (n) WHERE n.id IS NOT NULL RETURN n.id AS id, n.path AS path, n.name AS name, n.title AS title ORDER BY id")
    finally:
        graph.close()
    generation.rng.shuffle(rows)
    output = ROOT/"results/v2/phase2"
    save_snapshot(output/"split_generation", snapshot(None, "router_tuning_generation", generation_seed=policy["seed"],
        exclusion_hashes={n:sha256(directory/(n+".csv")) for n in policy["excluded_splits"]}))
    write_csv(target, rows)
    (output/"entity_catalog.json").write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    manifest_path = directory/"manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["splits"]["router-tuning"] = dict(count=len(rows), sha256=sha256(target), seed=policy["seed"],
        source="fresh graph-verified generator", excluded_repositories=["apache/airflow"],
        disjoint_normalized_questions=True, disjoint_complete_expected_entity_sets=True)
    manifest_path.write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print("Fresh router-tuning split and KG entity catalog frozen")


if __name__ == "__main__":
    prepare()

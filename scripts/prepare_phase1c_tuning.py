"""Version and enlarge tuning-only data; protected split gold is never changed."""
import json
import random
import hashlib
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import ROOT
from src.graph import Graph
from src.benchmark_gen import generate_benchmark as generation
from src.evaluation.metrics_v2 import gold_completeness
from src.evaluation.reproducibility import read_csv, write_csv, sha256, save_snapshot
from scripts.prepare_router_tuning import RepositoryCandidates
from scripts.audit_phase1b import audit, overlaps, exclusion_rows, norm, RULE, SPLITS

OUT = ROOT / "results/v2/phase1c/split_generation"
SEED, TARGET, MAX_ATTEMPTS = 20261012, 20, 600


def tuples(value):
    return tuple(tuples(v) for v in value) if isinstance(value, list) else value


def save(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2)+"\n", encoding="utf-8")
    temp.replace(path)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    archive, target = SPLITS/"router-tuning_v1.csv", SPLITS/"router-tuning.csv"
    if sha256(archive) != "fee8bab59925109abfff7d7b579fa1df92800962403200116fd329f2ce539aa8":
        raise RuntimeError("v1 archive mismatch")
    if (OUT/"final.json").exists():
        final = json.loads((OUT/"final.json").read_text())
        if final["sha256"] != sha256(target):
            raise RuntimeError("Completed v2 was changed")
        print("Already frozen; no regeneration", final)
        return
    protected = exclusion_rows()
    excluded = [r for rows in protected.values() for r in rows]
    old = read_csv(archive)
    reaudit = audit(old)
    removed = {r["question_id"] for c in reaudit["checks"].values() for r in c["overlaps"]}
    retained = [r for r in old if r["question_id"] not in removed]
    retained_count = len(retained)
    save(OUT/"removed_questions.json", [r for r in old if r["question_id"] in removed])
    save_snapshot(OUT, dict(seed=SEED, target_per_category=TARGET, max_attempts_per_category=MAX_ATTEMPTS,
        repository_policy="All six graph repositories including Airflow; prioritize underrepresented repositories in each category",
        rule=RULE, archive_sha256=sha256(archive), protected_hashes={n:sha256(SPLITS/(n+".csv")) for n in protected},
        source_hashes={p:sha256(ROOT/p) for p in ["scripts/prepare_phase1c_tuning.py", "scripts/audit_phase1b.py",
            "scripts/prepare_router_tuning.py", "src/benchmark_gen/generate_benchmark.py"]}))
    checkpoint = OUT/"checkpoint.json"
    state = json.loads(checkpoint.read_text()) if checkpoint.exists() else dict(rows=retained, attempts={}, rejected={})
    generation.rng = random.Random(SEED)
    if "rng" in state:
        generation.rng.setstate(tuples(state["rng"]))
    rows = state["rows"]
    seen = {norm(r["question"]) for r in rows}
    graph = Graph()
    try:
        repositories = [r["id"] for r in graph.query("MATCH (r:Repository) RETURN r.id AS id ORDER BY id")]
        expected = {"apache/airflow", "dotnet/eShop", "mlflow/mlflow", "openmrs/openmrs-core",
                    "spring-projects/spring-petclinic", "synthetic-org/platform"}
        if not expected <= set(repositories):
            raise RuntimeError("Required repositories absent: " + str(expected-set(repositories)))
        candidates = {repo:RepositoryCandidates(graph, repo) for repo in sorted(expected)}
        for category, generator in generation.GENERATORS.items():
            failures = Counter()
            while sum(r["category"] == category for r in rows) < TARGET and state["attempts"].get(category, 0) < MAX_ATTEMPTS:
                counts = Counter(r["source_repo"] for r in rows if r["category"] == category)
                # Failed discoveries gradually lose priority, avoiding a single exhausted repository blocking others.
                repo = min(candidates, key=lambda p:(counts[p]+failures[p]/20, p))
                state["attempts"][category] = state["attempts"].get(category, 0)+1
                candidate = generator(candidates[repo])
                reason = None
                if candidate is None or not generation.validate_row(candidate):
                    reason = "no_valid_candidate"
                elif norm(candidate["question"]) in seen:
                    reason = "duplicate_text"
                else:
                    identifier = "router-tuning-"+hashlib.sha256(norm(candidate["question"]).encode()).hexdigest()[:16]
                    candidate.update(id=identifier, question_id=identifier, generation_seed=SEED)
                    if overlaps([candidate], excluded):
                        reason = "protected_subject_overlap"
                if reason:
                    failures[repo] += 1
                    key = category+"/"+reason
                    state["rejected"][key] = state["rejected"].get(key,0)+1
                else:
                    complete, why = gold_completeness(candidate)
                    candidate.update(gold_complete=complete, gold_complete_reason=why)
                    rows.append(candidate)
                    seen.add(norm(candidate["question"]))
                    print(category, sum(r["category"] == category for r in rows), repo, flush=True)
                state["rng"] = generation.rng.getstate()
                save(checkpoint,state)  # At least one checkpoint after every accepted question.
    finally:
        graph.close()
    final_audit = audit(rows)
    if final_audit["status"] == "FAIL":
        raise RuntimeError("Final subject audit failed; refusing to freeze v2")
    if sha256(target) != sha256(archive):
        raise RuntimeError("Current split changed unexpectedly; refusing overwrite")
    write_csv(OUT/"router-tuning_v2.csv", rows)
    target.write_bytes((OUT/"router-tuning_v2.csv").read_bytes())
    manifest_path = SPLITS/"manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["splits"]["router-tuning_v1"] = dict(manifest["splits"]["router-tuning"], file="router-tuning_v1.csv")
    manifest["splits"]["router-tuning"] = dict(version=2, count=len(rows), sha256=sha256(target),
        usage="tuning-only; post-hoc primary-subject rule; not held-out evidence", seed=SEED,
        retained_v1_seed=20261009, retained_v1_questions=retained_count, removed_v1_questions=sorted(removed),
        source="v1 retained rows plus fresh graph-verified generation", excluded_repositories=[],
        primary_entity_disjointness="PASS_DETECTABLE_SUBJECTS", audit_rule=RULE,
        disjoint_normalized_questions=True, audit="results/v2/phase1c/disjointness.json")
    save(manifest_path, manifest)
    final_audit.update(hashes={n:sha256(SPLITS/(n+".csv")) for n in ("router-tuning",*protected)},
                       audited_split="router-tuning", audited_split_sha256=sha256(target))
    save(OUT.parent/"disjointness.json",final_audit)
    final = dict(count=len(rows), sha256=sha256(target), retained=retained_count, removed=sorted(removed),
                 added=len(rows)-retained_count, categories=Counter(r["category"] for r in rows),
                 repositories=Counter(r["source_repo"] for r in rows), attempts=state["attempts"], rejections=state["rejected"],
                 target=TARGET, missing_target={c:TARGET-sum(r["category"]==c for r in rows) for c in generation.GENERATORS
                                               if sum(r["category"]==c for r in rows)<TARGET},
                 maximum_note="Target reached where reported; no exhaustive mathematical maximum claimed. A shortfall is the achieved count within the recorded candidate-search budget.")
    save(OUT/"final.json",final)
    print(json.dumps(final,indent=2))


if __name__ == "__main__":
    main()

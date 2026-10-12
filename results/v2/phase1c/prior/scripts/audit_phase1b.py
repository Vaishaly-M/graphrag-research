"""Read-only Phase 1B audit. Held-out files are read solely for split exclusion checks."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import ROOT
from src.evaluation.metrics_v2 import gold_completeness, items, truth
from src.evaluation.reproducibility import read_csv, write_csv, sha256

OUT = ROOT / "results/v2/phase1b"
SPLITS = ROOT / "data/benchmark/splits_v2"


def norm(text):
    return re.sub(r"\s+", " ", str(text).casefold()).strip()


def anchors(row):
    """Repository-scoped query subjects, not whole expected-answer sets.

    Code/doc fragments use their returned file identity; repository-only questions use the repo.
    Human questions have no structured subjects: match known subjects against text.
    This establishes detectable overlap, not semantic disjointness of paraphrases.
    """
    params = json.loads(row.get("params") or "{}")
    keys = ("path", "commit", "developer", "title", "issue_number", "directory")
    found = [(k, norm(params[k]).removeprefix("email:")) for k in keys if params.get(k) is not None]
    if not found and "fragment" in params:
        if row.get("category") in {"code_retrieval", "documentation_lookup"}:
            return [("path", norm(p)) for p in items(row.get("expected_entities"))]
        return []  # A search keyword (e.g. 'failed') is not an entity identity.
    return found or ([("repository", norm(params["repo"]))] if params.get("repo") else [])


def overlaps(tuning, others):
    found = []
    for a in tuning:
        repo = norm(a.get("source_repo") or a.get("repo"))
        for b in others:
            aid, bid = a.get("question_id") or a["id"], b.get("question_id") or b.get("id")
            if norm(a["question"]) == norm(b["question"]):
                found.append(dict(question_id=aid, other_question_id=bid, check="normalized_text", entity=None))
            if repo != norm(b.get("source_repo") or b.get("repo")):
                continue
            subjects = set(anchors(b))
            for kind, entity in anchors(a):
                # Subject matching against question text also covers unstructured human questions.
                pattern = r"(?<![\w])" + re.escape(entity) + r"(?![\w])"
                if (kind, entity) in subjects or (kind != "repository" and re.search(pattern, norm(b["question"]))):
                    found.append(dict(question_id=aid, other_question_id=bid, check="primary_entity",
                                      entity_type=kind, entity=entity, repository=repo))
    return found


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((SPLITS / "manifest.json").read_text(encoding="utf-8"))
    tuning = read_csv(SPLITS / "router-tuning.csv")
    hashes, checks, all_repos = {}, {}, set()
    for name in ("router-tuning", "development", "validation", "hidden-test", "human-test"):
        path = SPLITS / (name + ".csv")
        hashes[name] = sha256(path)
        if hashes[name] != manifest["splits"][name]["sha256"]:
            raise RuntimeError("Frozen split hash mismatch: " + name)
        if name == "router-tuning":
            continue
        rows = read_csv(path)
        all_repos.update(r.get("source_repo") or r.get("repo") for r in rows)
        matches = overlaps(tuning, rows)
        checks[name] = dict(status="FAIL" if matches else "PASS_DETECTABLE_SUBJECTS",
                            text_overlaps=sum(m["check"] == "normalized_text" for m in matches),
                            primary_entity_overlaps=sum(m["check"] == "primary_entity" for m in matches),
                            overlaps=matches)
    categories = Counter(r["category"] for r in tuning)
    repositories = Counter(r["source_repo"] for r in tuning)
    expected_categories = {"structure", "code_retrieval", "documentation_lookup", "dependency_analysis",
                           "issue_pr_analysis", "developer_activity", "multi_hop"}
    report = dict(status="FAIL" if any(c["overlaps"] for c in checks.values()) else "PASS_DETECTABLE_SUBJECTS",
                  checks=checks, hashes=hashes, count=len(tuning), categories=categories, repositories=repositories,
                  missing_categories=sorted(expected_categories-set(categories)),
                  missing_repositories=sorted(all_repos-set(repositories)),
                  generation_seeds=sorted({r["generation_seed"] for r in tuning}),
                  policy="tuning-only; no gold edits; held-out metadata used only for exclusion checking",
                  limitation="Human primary entities are not annotated; literal subject matching cannot prove semantic disjointness.")
    (OUT / "disjointness.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    # Extend the existing diagnostic only; do not evaluate any held-out split again.
    historical = {r["id"]: r for r in read_csv(ROOT / "data/benchmark/benchmark_300.csv")}
    saved = {(r["system"], r["question_id"]): r for r in read_csv(ROOT / "results/v2/rescore_per_question.csv")}
    flips = [r for r in read_csv(ROOT / "results/v2/changed_verdicts.csv") if r["system"] == "adaptive_hybrid_graphrag"]
    if len(flips) != 25:
        raise RuntimeError("Expected the existing 25-flip adaptive diagnostic")
    table = []
    for flip in flips:
        qid = flip["question_id"]
        original, metric = historical[qid], saved[(flip["system"], qid)]
        complete, reason = gold_completeness(original)
        predicted, missing, extra = (items(metric[k]) for k in ("predicted_entities", "missing_entities", "extra_entities"))
        recall = int(not truth(metric["is_error"]) and not truth(metric["abstained"]) and not missing
                     and not any(c.startswith("negated_expected_entity:") for c in items(metric["contradictions"])))
        table.append(dict(question_id=qid, gold_length=len(items(original["expected_entities"])),
                          returned_length=len(predicted), gold_complete=complete, gold_complete_reason=reason,
                          legacy_accuracy=float(metric["legacy_accuracy"]), recall_accuracy=recall,
                          strict_accuracy=int(metric["strict_accuracy"]),
                          strict_complete_accuracy=int(metric["strict_accuracy"]) if complete is True else None,
                          extra_entities=extra, extra_entity_count=len(extra)))
    write_csv(OUT / "diagnostic_25_flips.csv", table)
    nulls = [dict(question_id=r["question_id"], scope="historical_25_flips", reason=r["gold_complete_reason"])
             for r in table if r["gold_complete"] is None]
    nulls += [dict(question_id=r["question_id"], scope="router-tuning", reason=gold_completeness(r)[1])
              for r in tuning if gold_completeness(r)[0] is None]
    write_csv(OUT / "gold_complete_null.csv", nulls)
    summary = dict(original_flips=25, strict_flips_remaining=sum(r["legacy_accuracy"] != r["strict_accuracy"] for r in table),
                   known_complete_flips_remaining=sum(r["gold_complete"] is True and r["legacy_accuracy"] != r["strict_accuracy"] for r in table),
                   recall_flips_remaining=sum(r["legacy_accuracy"] != r["recall_accuracy"] for r in table),
                   unknown_completeness=sum(r["gold_complete"] is None for r in table),
                   note="Unknown completeness is excluded from strict-complete accuracy, never converted into a pass.")
    (OUT / "diagnostic_summary.json").write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")
    inputs = [ROOT / "results/v2/changed_verdicts.csv", ROOT / "results/v2/rescore_per_question.csv",
              ROOT / "data/benchmark/benchmark_300.csv", ROOT / "src/evaluation/metrics_v2.py", Path(__file__)]
    (OUT / "audit_snapshot.json").write_text(json.dumps(dict(split_hashes=hashes,
        inputs={p.relative_to(ROOT).as_posix(): sha256(p) for p in inputs},
        entity_rule=anchors.__doc__, diagnostic_system="adaptive_hybrid_graphrag", evaluation_runs=0), indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "checks"}, indent=2))
    for name, check in checks.items():
        print(name, check["status"], "text overlaps:", check["text_overlaps"],
              "primary entity overlaps:", check["primary_entity_overlaps"])
        for match in check["overlaps"]:
            print(json.dumps(match))
    print(json.dumps(summary, indent=2))
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())

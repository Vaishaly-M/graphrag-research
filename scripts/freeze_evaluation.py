"""Copy existing split memberships without modifying gold; validate human metadata."""
import json
import re
import shutil
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import ROOT
from src.evaluation.reproducibility import read_csv, write_csv, sha256
from src.evaluation.metrics_v2 import CATEGORY_MAP, PATH, HASH, EMAIL


def norm(s):
    return re.sub(r"\W+", " ", s.casefold()).strip()


def entities(s):
    return {m.group().casefold() for pattern in [PATH, HASH, EMAIL] for m in pattern.finditer(s)}


def main():
    source = ROOT / "data/benchmark"
    dest = source / "splits_v2"
    output = ROOT / "results/v2"
    dest.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    mapping = {"development": source/"splits/dev.csv", "validation": source/"splits/validation.csv",
               "hidden-test": source/"splits/hidden_test_answer_key.csv",
               "human-test": source/"Human Written Question.csv"}
    manifest = {"schema_version": 2, "policy": "retain existing memberships; no human tuning", "splits": {}}
    all_ids = set()
    for name, original in mapping.items():
        data = read_csv(original)
        ids = [r.get("question_id") or r.get("id") for r in data]
        if not all(ids) or len(ids) != len(set(ids)):
            raise ValueError("Missing/duplicate IDs: " + name)
        if all_ids & set(ids):
            raise ValueError("Overlapping split IDs: " + name)
        all_ids.update(ids)
        target = dest / (name + ".csv")
        if target.exists() and sha256(target) != sha256(original):
            raise RuntimeError("Frozen split differs: " + str(target))
        shutil.copyfile(original, target)
        manifest["splits"][name] = dict(count=len(data), sha256=sha256(target), source=str(original.relative_to(ROOT)))
    templates = read_csv(source / "benchmark_300.csv")
    template_ids = {r["id"] for r in templates}
    frozen_template_ids = all_ids - {r["question_id"] for r in read_csv(mapping["human-test"])}
    if frozen_template_ids != template_ids:
        raise ValueError("Template partition does not exactly cover source benchmark")
    human = read_csv(mapping["human-test"])
    columns = list(human[0])
    missing = []
    for r in human:
        required = [f for f in ["answerable", "expected_answer", "expected_entities", "required_facts", "answer_type", "gold_evidence"] if not r.get(f)]
        missing.append(dict(question_id=r["question_id"], repo=r["repo"], category=r["category"], question=r["question"],
                            missing_fields=";".join(required), answerable="", expected_answer="", expected_entities="",
                            required_facts="", answer_type="", gold_evidence=""))
    write_csv(output/"human_gold_needed.csv", missing)
    duplicates = [text for text, count in Counter(norm(r["question"]) for r in human).items() if count > 1]
    report = dict(columns=columns, n_rows=len(human), null_counts={c: sum(not r[c].strip() for r in human) for c in columns},
        duplicate_normalized_questions=duplicates, duplicate_ids=[], repositories=dict(Counter(r["repo"] for r in human)),
        categories=dict(Counter(r["category"] for r in human)),
        unknown_categories=sorted({r["category"] for r in human}-set(CATEGORY_MAP)),
        answerability="unknown for every row; cannot infer from question wording",
        missing_gold_ids=[r["question_id"] for r in missing], paraphrased_set="missing; no saved paraphrased CSV found",
        problems=["No answerability labels", "No gold answers or expected entities", "No required facts",
                  "No answer_type for per-category extraction", "No gold evidence for retrieval metrics",
                  "repo column differs from template source_repo; mapped in evaluator only",
                  "Human categories use display names; mapped in evaluator only"])
    (output/"human_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    comparisons = []
    for h in human:
        hn, he = norm(h["question"]), entities(h["question"])
        best = None
        for t in templates:
            tn, te = norm(t["question"]), entities(t["question"])
            text_score = SequenceMatcher(None, hn, tn).ratio()
            entity_score = len(he & te)/len(he | te) if he | te else 0.0
            flagged = hn == tn or text_score >= .90 or (bool(he) and entity_score >= .90)
            item = dict(human_id=h["question_id"], template_id=t["id"], human_question=h["question"],
                        template_question=t["question"], exact_match=hn == tn, text_similarity=text_score,
                        entity_similarity=entity_score, human_entities=sorted(he), template_entities=sorted(te),
                        flagged=flagged, entity_basis="question identifiers only; human gold entities unavailable")
            if flagged:
                comparisons.append(item)
            if best is None or text_score > best["text_similarity"]:
                best = item
        if best and not best["flagged"]:
            comparisons.append(best)
    write_csv(output/"leakage_review.csv", comparisons)
    manifest["paraphrased_set"] = None
    (dest/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    table = "\n".join(f"| {name} | {entry['count']} |" for name, entry in manifest["splits"].items())
    (dest/"README.md").write_text("""# Frozen evaluation splits

This is the single human-readable split count table.

| Split | Questions |
| --- | ---: |
"""+table+"""

Development is the only tuning set. Validation is for a locked selection check, not iterative tuning.
Hidden-test is the existing held-out template membership, with its unchanged gold key.
Human-test is never used for tuning; its gold and answerability annotations are missing.
All files are byte-identical copies of their source CSVs. Original IDs are retained.
The run harness sends only question text to systems. Oracle's existing template-label lookup remains unchanged;
human questions have no such labels. Missing human gold is N/A, never an invented answer or zero accuracy.

The old category table describes the entire benchmark; the main table describes hidden-test after
development and validation exclusions. Those denominators must be labeled explicitly in the paper.
Airflow is absent from development and validation; this denotes the split policy, not proof that later
code changes were blind to Airflow. Development/validation also lack structure and code_retrieval categories;
do not repair this imbalance by moving questions after viewing their results.

No saved paraphrased question set was found; none is generated in Phase 1.
Manifest hashes bind the frozen files. The separate results/v2/human_gold_needed.csv worksheet lists
missing annotation fields. Editing that worksheet does not change frozen gold; a later reviewed version
must be explicitly frozen before human scoring.
""",encoding="utf-8")
    print("Frozen split copies and human validation/leakage reports written.")


if __name__ == "__main__":
    main()

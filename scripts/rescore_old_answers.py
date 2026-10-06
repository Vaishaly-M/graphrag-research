"""Read-only diagnostic of historical answers; never a new paper result."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import ROOT
from src.evaluation.metrics_v2 import evaluate_row, summarize
from src.evaluation.reproducibility import read_csv, write_csv


def main():
    hidden = {r["id"]: r for r in read_csv(ROOT/"data/benchmark/splits/hidden_test_answer_key.csv")}
    dev = {r["id"]: r for r in read_csv(ROOT/"data/benchmark/splits/dev.csv")}
    summaries, changed, details = [], [], []
    paths = sorted((ROOT/"results/final_evaluation").glob("*_results.csv"))
    paths += sorted((ROOT/"results/ablations").glob("*/adaptive_hybrid_graphrag_results.csv"))
    for path in paths:
        ablation = "ablations" in path.parts
        group = "ablation/"+path.parent.name if ablation else path.stem.removesuffix("_results")
        gold = dev if ablation else hidden
        scored = []
        for record in read_csv(path):
            qid = record.get("question_id") or record["id"]
            row = {**record, **gold[qid], "question_id": qid}
            metric = evaluate_row(row)
            metric["system"] = group
            scored.append(metric)
            details.append(dict(source=str(path.relative_to(ROOT)), **metric))
            if metric["legacy_accuracy"] != metric["strict_accuracy"]:
                changed.append(dict(system=group, question_id=qid, source=str(path.relative_to(ROOT)),
                    legacy_accuracy=metric["legacy_accuracy"], strict_accuracy=metric["strict_accuracy"],
                    missing_entities=metric["missing_entities"], extra_entities=metric["extra_entities"],
                    contradictions=metric["contradictions"], is_error=metric["is_error"]))
        summaries.extend(summarize(scored))
    write_csv(ROOT/"results/v2/rescore_old_answers.csv", summaries)
    write_csv(ROOT/"results/v2/changed_verdicts.csv", changed,
              fields=["system", "question_id", "source", "legacy_accuracy", "strict_accuracy",
                      "missing_entities", "extra_entities", "contradictions", "is_error"])
    write_csv(ROOT/"results/v2/rescore_per_question.csv", details)
    print(f"Diagnostic rescoring complete: {len(summaries)} system/variant groups; {len(changed)} changed verdicts")


if __name__ == "__main__":
    main()

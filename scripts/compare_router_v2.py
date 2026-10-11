"""Fresh-set old-adaptive/new-router comparison, after selection only."""
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.common import ROOT
from src.evaluation.reproducibility import read_csv, write_csv


def main():
    output=ROOT/"results/v2/phase2"
    if not (output/"frozen_router.json").exists():
        raise RuntimeError("No verified frozen router; comparison cannot run")
    for name in ["adaptive_hybrid_graphrag","adaptive_hybrid_graphrag_v2"]:
        subprocess.run([sys.executable,"-B",str(ROOT/"scripts/run_eval.py"),name,"router-tuning",
            "--run-name","phase2_compare_"+name,"--repeats","1","--no-cache"],check=True,cwd=ROOT)
    old={r["question_id"]:r for r in read_csv(ROOT/"results/v2/phase2_compare_adaptive_hybrid_graphrag/per_question_metrics.csv")}
    new=read_csv(ROOT/"results/v2/phase2_compare_adaptive_hybrid_graphrag_v2/per_question_metrics.csv")
    comparison=[dict(question_id=r["question_id"],old_recall_accuracy=old[r["question_id"]]["recall_accuracy"],
        new_recall_accuracy=r["recall_accuracy"],old_strict_accuracy=old[r["question_id"]]["strict_accuracy"],
        new_strict_accuracy=r["strict_accuracy"],old_latency_s=old[r["question_id"]]["latency_s"],
        new_latency_s=r["latency_s"]) for r in new]
    write_csv(output/"old_vs_router_v2.csv",comparison)


if __name__ == "__main__":
    main()

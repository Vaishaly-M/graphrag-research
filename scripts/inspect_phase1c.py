"""Human text-only template coverage and five explicitly requested historical gold reviews."""
import json
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.common import ROOT
from src.graph import Graph
from src.systems.query_registry import match_registered_query
from src.evaluation.reproducibility import read_csv, write_csv, sha256, save_snapshot
from src.evaluation.metrics_v2 import items

OUT = ROOT/"results/v2/phase1c/inspection"


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    human_path=ROOT/"data/benchmark/splits_v2/human-test.csv"
    save_snapshot(OUT,dict(human_sha256=sha256(human_path),
        template_registry_sha256=sha256(ROOT/"src/systems/query_registry.py"),
        inspection_script_sha256=sha256(Path(__file__)),
        human_protocol="Question text only; boolean template match; no gold, scoring, model calls or tuning",
        historical_review_ids=["code_retrieval-"+n for n in ["003","005","013","018","033"]],
        historical_protocol="Inspect explicitly requested five questions, saved entities and graph fragment matches; no gold edits, no model calls"))
    matched=[]
    for raw in read_csv(human_path):
        # Select only text/descriptive columns; no answer/gold field is accessed.
        row={k:raw[k] for k in ("question_id","question","category","repo")}
        matched.append(dict(question_id=row["question_id"],category=row["category"],repository=row["repo"],
                            template_matches=match_registered_query(row["question"]) is not None))
        write_csv(OUT/"human_template_matches.csv",matched)
    summaries=[]
    for group in ("ALL","category","repository"):
        values=["ALL"] if group=="ALL" else sorted({r[group] for r in matched})
        for value in values:
            part=[r for r in matched if group=="ALL" or r[group]==value]
            n=sum(r["template_matches"] for r in part)
            summaries.append(dict(group=group,value=value,n=len(part),matched=n,unmatched=len(part)-n,match_rate=n/len(part)))
    write_csv(OUT/"human_template_summary.csv",summaries)
    ids={"code_retrieval-"+n for n in ("003","005","013","018","033")}
    historical={r["id"]:r for r in read_csv(ROOT/"data/benchmark/benchmark_300.csv") if r["id"] in ids}
    saved={r["question_id"]:r for r in read_csv(ROOT/"results/v2/rescore_per_question.csv")
           if r["question_id"] in ids and r["system"]=="adaptive_hybrid_graphrag"}
    path=OUT/"five_flip_review.json"
    reviews=json.loads(path.read_text()) if path.exists() else []
    graph=Graph()
    try:
        for qid in sorted(ids-{r["question_id"] for r in reviews}):
            row=historical[qid]
            params=json.loads(row["params"])
            query="""MATCH (:Repository {id:$repo})-[:CONTAINS_FILE]->(f:File)
                     WHERE f.content CONTAINS $fragment
                     RETURN DISTINCT f.path AS path ORDER BY path"""
            matches=[r["path"] for r in graph.query(query,repo=params["repo"],fragment=params["fragment"])]
            gold=items(row["expected_entities"])
            returned=items(saved[qid]["predicted_entities"])
            review=dict(question_id=qid,question=row["question"],repository=params["repo"],fragment=params["fragment"],
                        gold=gold,returned_entities=returned,graph_matching_files=matches,
                        graph_fragment_in_multiple_files=len(matches)>1,
                        gold_is_only_valid_answer_in_current_graph=set(matches)==set(gold) and len(matches)==1,
                        gold_matches_current_graph=set(matches)==set(gold),
                        returned_valid_in_current_graph=sorted(set(returned)&set(matches)),
                        returned_not_matching_current_graph=sorted(set(returned)-set(matches)),
                        original_generation_cypher=row["cypher"],review_query=query,
                        flag_for_user_review=True,
                        limitation="Current graph inspection, not proof of historical snapshot truth; gold remains unchanged.")
            reviews.append(review)
            path.write_text(json.dumps(reviews,indent=2)+"\n",encoding="utf-8")
            print(json.dumps(review),flush=True)
    finally:
        graph.close()
    write_csv(OUT/"five_flip_review.csv",reviews)
    print(json.dumps(summaries,indent=2))


if __name__=="__main__":
    main()

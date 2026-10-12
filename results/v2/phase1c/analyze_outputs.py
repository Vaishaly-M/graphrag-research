"""Offline Phase 1C validation/description. No model or graph calls."""
import json
import sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from src.common import read_jsonl
from src.evaluation.reproducibility import read_csv,sha256,source_hashes
from scripts.derive_oracle_routes import active_records,derive
OUT=ROOT/"results/v2/phase1c"


def analyze_mode(name):
    directory=OUT/name
    if not (directory/"progress.json").exists():
        return dict(status="NOT_RUN")
    progress=json.loads((directory/"progress.json").read_text())
    config=json.loads((directory/"config_snapshot.json").read_text())
    history=read_jsonl(directory/"outcomes.jsonl")
    records=active_records(history)
    groups={}
    for r in records:
        groups.setdefault(r["question_id"],{})[r["route"]]=r
    complete={q:routes for q,routes in groups.items() if set(routes)=={"graph","vector","hybrid"}}
    oracle=derive([r for routes in complete.values() for r in routes.values()])
    different_answers=sum(len({r["answer"] for r in routes.values()})>1 for routes in complete.values())
    all_three_different=sum(len({r["answer"] for r in routes.values()})==3 for routes in complete.values())
    different_recall=sum(len({r["recall_accuracy"] for r in routes.values()})>1 for routes in complete.values())
    known=[routes for routes in complete.values() if all(r["gold_complete"] is True for r in routes.values())]
    different_strict=sum(len({r["strict_accuracy"] for r in routes.values()})>1 for routes in known)
    route_counts={route:sum(routes[route]["recall_accuracy"]==1 for routes in complete.values()) for route in ("graph","vector","hybrid")}
    dominating=[route for route in route_counts if all(routes[route]["recall_accuracy"] >= max(r["recall_accuracy"] for r in routes.values())
                                                     for routes in complete.values())] if complete else []
    oracle_recall=sum(r["oracle_best_accuracy"] for r in oracle)
    best_single=max(route_counts.values(),default=0)
    strict_oracle=[r["oracle_best_strict_accuracy"] for r in oracle if r["oracle_best_strict_accuracy"] is not None]
    strict_counts={route:sum(routes[route]["strict_accuracy"]==1 for routes in known) for route in ("graph","vector","hybrid")}
    strict_dominating=[route for route in strict_counts if all(routes[route]["strict_accuracy"]>=
        max(r["strict_accuracy"] for r in routes.values()) for routes in known)] if known else []
    checks={
        "run_source_hashes_match":config["source_hashes"]==source_hashes(),
        "only_current_tuning_ids":all(q in {r["question_id"] for r in read_csv(ROOT/"data/benchmark/splits_v2/router-tuning.csv")} for q in groups),
        "strict_na_unless_known_complete":all((r["strict_accuracy"] is not None)==(r["gold_complete"] is True) for r in records),
        "errors_incorrect":all(r["recall_accuracy"]==0 and r["strict_accuracy"] in (None,0) for r in records if r["is_error"]),
        "forced_route_preserved":all(r.get("executed_retrieval_route")==r["route"] for r in records if not r["is_error"]),
        "latency_excludes_pacing_backoff":all(abs(r["latency_s"]-max(0,r["total_wall_s"]-r["sleep_wait_s"]))<1e-6 for r in records),
        "complete_count_matches":len(complete)==progress["questions_with_all_routes"],
        "oracle_dominates_each_route":all(o["oracle_best_accuracy"]>=r["recall_accuracy"] and
            (r["strict_accuracy"] is None or o["oracle_best_strict_accuracy"]>=r["strict_accuracy"])
            for o in oracle for r in complete[o["question_id"]].values()),
        "no_templates_enforced":all(not r.get("templates_enabled",True) and r.get("answer_generation_mode")!="deterministic_graph" and
            all(a["rung"]!="registered_template" for a in r.get("graph_attempts",[])) for r in records if not r["is_error"])
            if config["mode"]=="no-templates" else True,
        "full_denominator_if_complete":len(complete)==140 if progress["status"].startswith("COMPLETE") else True,
    }
    old={(r["question_id"],r["route"]):r for r in read_jsonl(ROOT/"results/v2/phase1b/route_outcomes/outcomes.jsonl")}
    checks["imported_answers_and_timings_unchanged"]=all(
        r["answer"]==old[(r["question_id"],r["route"])]["answer"] and
        r["latency_s"]==old[(r["question_id"],r["route"])]["latency_s"] for r in records if r.get("imported"))
    local=[r for r in history if not r.get("imported")]
    checks["all_local_api_events_logged"]=len(read_jsonl(directory/"llm_events.jsonl"))==sum(len(r["retry_events"]) for r in local)
    result=dict(status=progress["status"],progress=progress,complete_questions=len(complete),
        questions_with_any_different_answers=different_answers,questions_with_three_distinct_answers=all_three_different,
        questions_with_different_recall_correctness=different_recall,questions_with_different_strict_correctness=different_strict,
        strict_comparison_denominator=len(known),oracle_distribution=Counter(r["oracle_route"] or "none" for r in oracle),
        oracle_recall_accuracy=oracle_recall/len(complete) if complete else None,
        oracle_strict_accuracy=sum(strict_oracle)/len(strict_oracle) if strict_oracle else None,
        best_single_route_correct=best_single,oracle_correct=oracle_recall,oracle_gain_questions=oracle_recall-best_single,
        dominating_routes=dominating,route_recall_counts=route_counts,
        strict_dominating_routes=strict_dominating,route_strict_counts=strict_counts,
        strict_oracle_gain_questions=sum(strict_oracle)-max(strict_counts.values(),default=0),
        imported_outcomes=sum(bool(r.get("imported")) for r in records),
        graph_hybrid_identical=sum(rs["graph"]["answer"]==rs["hybrid"]["answer"] for rs in complete.values()),
        local_api_attempts=sum(r["n_attempts"] for r in local),local_cache_hits=sum(r["n_cache_hits"] for r in local),
        total_pacing_s=sum(r["pacing_sleep_s"] for r in local),total_backoff_s=sum(r["backoff_sleep_s"] for r in local),
        checks=checks,all_checks_pass=all(checks.values()))
    (directory/"analysis.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    return result


def main():
    splits=ROOT/"data/benchmark/splits_v2"
    old_manifest=json.loads((OUT/"prior/data/benchmark/splits_v2/manifest.json").read_text())
    v1={r["question_id"]:r for r in read_csv(splits/"router-tuning_v1.csv")}
    v2={r["question_id"]:r for r in read_csv(splits/"router-tuning.csv")}
    checks=dict(protected_splits_unchanged=all(sha256(splits/(name+".csv"))==old_manifest["splits"][name]["sha256"]
        for name in ("development","validation","hidden-test","human-test")),
        v1_byte_hash_unchanged=sha256(splits/"router-tuning_v1.csv")==old_manifest["splits"]["router-tuning"]["sha256"],
        retained_rows_unchanged=all(v1[q]=={k:v2[q][k] for k in v1[q]} for q in set(v1)&set(v2)),
        only_flagged_question_removed=set(v1)-set(v2)=={"router-tuning-c6dc0e1b1b05a2df"},
        final_split_hash_matches=sha256(splits/"router-tuning.csv")==json.loads((splits/"manifest.json").read_text())["splits"]["router-tuning"]["sha256"])
    modes={name:analyze_mode(name) for name in ("with_templates","no_templates")}
    result=dict(checks=checks,modes=modes,all_available_checks_pass=all(checks.values()) and all(m.get("all_checks_pass",True) for m in modes.values()))
    (OUT/"validation.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(dict(checks=checks,modes={k:{f:v.get(f) for f in ("status","complete_questions","oracle_distribution",
        "oracle_gain_questions","dominating_routes","all_checks_pass")} for k,v in modes.items()}),indent=2))
    if not result["all_available_checks_pass"]:
        raise RuntimeError("Unexpected Phase 1C output integrity failure")


if __name__=="__main__":
    main()

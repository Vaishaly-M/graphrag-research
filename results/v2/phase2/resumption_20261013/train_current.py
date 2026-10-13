"""Category-stratified OOF selection; only the fresh router-tuning split is accepted."""
import hashlib
import json
import sys
import time
from pathlib import Path
import numpy as np
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import f1_score, accuracy_score, recall_score
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from src.common import ROOT, read_jsonl, append_jsonl
from src.evaluation.reproducibility import read_csv, write_csv, sha256, save_snapshot, snapshot, source_hashes
from src.evaluation.telemetry import Measurement, measured
from src.systems.router_v2 import RouterV2, EntityCatalog, ROUTES, FEATURES, train_artifact, EXEMPLARS
from src.llm import GeminiClient, EmptyModelResponse
from scripts.derive_oracle_routes import active_records
from scripts.measure_phase2_routes import usable_timing


def main():
    output = ROOT/"results/v2/phase2/resumption_20261013"
    benchmark = ROOT/"data/benchmark/splits_v2/router-tuning.csv"
    policy_path = output/"selection_rule.json"
    policy = json.loads(policy_path.read_text())
    manifest = json.loads((benchmark.parent/"manifest.json").read_text())
    if sha256(benchmark) != manifest["splits"]["router-tuning"]["sha256"]:
        raise RuntimeError("Fresh tuning split hash mismatch")
    questions = read_csv(benchmark)
    oracle = {r["question_id"]:r for r in read_csv(output/"route_outcomes/oracle_routes.csv")}
    outcomes = {(r["question_id"],r["route"]):r for r in active_records(read_jsonl(output/"route_outcomes/outcomes.jsonl"))}
    if set(oracle) != {r["question_id"] for r in questions}:
        raise RuntimeError("Oracle questions differ from fresh tuning split")
    if any(not usable_timing(outcomes[(q["question_id"],r)]) for q in questions for r in ROUTES):
        raise RuntimeError("Missing usable route timings; infrastructure/unknown/cache outcomes forbidden")
    if any(r.get("mode") != "no-templates" for r in outcomes.values()):
        raise RuntimeError("Phase 2 requires no-template outcomes")
    records = json.loads((output/"entity_catalog.json").read_text(encoding="utf-8"))
    catalog = EntityCatalog(records)
    from sentence_transformers import SentenceTransformer
    encoder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    base = RouterV2(catalog, encoder)
    features, embeddings, feature_costs = [], [], []
    for q in questions:
        start = time.perf_counter()
        f, _, e = base.features_for(q["question"])
        features.append(f)
        embeddings.append(e)
        feature_costs.append(time.perf_counter()-start)
    feature_snapshot = output / "feature_snapshot.json"
    if not feature_snapshot.exists():
        feature_snapshot.write_text(json.dumps([dict(question_id=q["question_id"], features=f,
            embedding=np.asarray(e).tolist(), feature_time_s=t) for q,f,e,t in
            zip(questions,features,embeddings,feature_costs)],indent=2)+"\n",encoding="utf-8")
    llm = GeminiClient()
    llm.cache_enabled = True
    llm.cache_dir = output / "router_cv/response_cache"
    llm.cache_namespace = "shared"
    labels = [oracle[q["question_id"]]["oracle_route"] for q in questions]
    categories = [q["category"] for q in questions]
    if min(categories.count(c) for c in set(categories)) < policy["folds"]:
        raise RuntimeError("Too few examples for five category-stratified folds")
    save_snapshot(output/"router_cv", snapshot(benchmark, "router_v2_cv", policy_sha256=sha256(policy_path),
        oracle_sha256=sha256(output/"route_outcomes/oracle_routes.csv"), source_hashes=source_hashes(),
        training_script_sha256=sha256(Path(__file__)), mode="no-templates",
        llm_router_model=llm.model, llm_router_client="GeminiClient",
        catalog_sha256=sha256(output/"entity_catalog.json")))
    oof = read_jsonl(output/"router_cv/oof_checkpoint.jsonl")
    completed = {(r["fold"],r["variant"],r["question_id"]) for r in oof}
    splitter = StratifiedKFold(n_splits=policy["folds"], shuffle=True, random_state=policy["seed"])
    for fold, (train, test) in enumerate(splitter.split(questions,categories)):
        usable = [i for i in train if labels[i] in ROUTES]
        for variant in policy["variants"]:
            artifact = train_artifact(variant,[features[i] for i in usable],[embeddings[i] for i in usable],
                [labels[i] for i in usable]) if variant in {"knn","logistic"} else None
            router = RouterV2(catalog,encoder,variant=variant,artifact=artifact,llm=llm,knn_k=policy["knn_k"])
            for i in test:
                q = questions[i]
                if (fold,variant,q["question_id"]) in completed:
                    continue
                start = time.perf_counter()
                router_error = None
                try:
                    measurement = Measurement(question_id=q["question_id"],system="router_"+variant,
                            event_path=output/"router_cv/llm_events.jsonl")
                    with measured(measurement):
                        scores = router.scores_for(q["question"],features[i],embeddings[i])
                except (ValueError, TypeError, RuntimeError) as exc:
                    # Production raises on malformed routing output; do not turn it into hybrid success.
                    if variant != "llm" or not isinstance(exc, (ValueError, TypeError, EmptyModelResponse)):
                        raise
                    router_error = type(exc).__name__
                    scores = np.zeros(len(ROUTES))
                if measurement.n_cache_hits:
                    raise RuntimeError("Uncheckpointed cached router response has no original inference timing; do not select on cache latency")
                overhead = time.perf_counter()-start-measurement.pacing_sleep_s-measurement.backoff_sleep_s+feature_costs[i]
                oof.append(dict(question_id=q["question_id"],fold=fold,variant=variant,
                    oracle_route=labels[i], scores=dict(zip(ROUTES,map(float,scores))), features=features[i],
                    router_time_s=overhead, router_error=router_error))
                append_jsonl(output/"router_cv/oof_checkpoint.jsonl",oof[-1])
                print("CV",fold,variant,q["question_id"],flush=True)
    write_csv(output/"oof_scores.csv",oof)
    candidates, traces = [], []
    for variant in policy["variants"]:
        subset = [r for r in oof if r["variant"]==variant]
        for tau in policy["tau_values"]:
            correct, regret, elapsed, always, truth_labels, predicted = [],[],[],[],[],[]
            for r in subset:
                qid = r["question_id"]
                if r.get("router_error"):
                    correct.append(0.)
                    regret.append(float(oracle[qid]["oracle_best_accuracy"]))
                    elapsed.append(r["router_time_s"])
                    always.append(float(outcomes[(qid,"hybrid")]["latency_s"]))
                    if r["oracle_route"]:
                        truth_labels.append(r["oracle_route"])
                        predicted.append("router_error")
                    traces.append(dict(question_id=qid,variant=variant,tau=tau,selected_route=None,
                        executed_route=None,fallback_used=False,recall_accuracy=0.,
                        router_time_s=r["router_time_s"],estimated_latency_s=r["router_time_s"],
                        router_error=r["router_error"]))
                    continue
                route = max(ROUTES,key=lambda k:r["scores"][k])
                if r["scores"][route]<tau:
                    route="hybrid"
                initial = outcomes[(qid,route)]
                weak_graph = route=="graph" and not initial.get("graph_retrieval_count")
                weak_vector = route=="vector" and (not initial.get("vector_retrieval_count") or
                    float(initial.get("vector_max_score") or 0)<policy["minimum_vector_score"])
                fallback = weak_graph or weak_vector
                selected = outcomes[(qid,"hybrid")] if fallback else initial
                accuracy = 0 if initial["is_error"] or selected["is_error"] else (selected["recall_accuracy"] or 0)
                correct.append(accuracy)
                regret.append(float(oracle[qid]["oracle_best_accuracy"])-accuracy)
                cost = float(selected["latency_s"])+r["router_time_s"]
                if fallback:
                    cost += float(initial["retrieval_time_s"])
                elapsed.append(cost)
                always.append(float(outcomes[(qid,"hybrid")]["latency_s"]))
                if r["oracle_route"]:
                    truth_labels.append(r["oracle_route"])
                    predicted.append(route)
                traces.append(dict(question_id=qid,variant=variant,tau=tau,selected_route=route,
                    executed_route="hybrid" if fallback else route,fallback_used=fallback,
                    recall_accuracy=accuracy,router_time_s=r["router_time_s"],estimated_latency_s=cost))
            candidate = dict(variant=variant,tau=tau,recall_accuracy=float(np.mean(correct)),
                routing_regret=float(np.mean(regret)),latency_savings_s=float(np.mean(always)-np.mean(elapsed)),
                macro_f1=float(f1_score(truth_labels,predicted,labels=list(ROUTES),average="macro",zero_division=0)))
            current_traces = [t for t in traces if t["variant"] == variant and t["tau"] == tau]
            strict_values = []
            for t in current_traces:
                qid = t["question_id"]
                if outcomes[qid,"graph"].get("gold_complete") is not True:
                    continue
                if t.get("router_error"):
                    strict_values.append(0.)
                else:
                    initial = outcomes[qid,t["selected_route"]]
                    selected = outcomes[qid,t["executed_route"]]
                    strict_values.append(0. if initial["is_error"] or selected["is_error"] else float(selected["strict_accuracy"] or 0))
            route_recalls = recall_score(truth_labels,predicted,labels=list(ROUTES),average=None,zero_division=0)
            candidate.update(routing_accuracy=float(accuracy_score(truth_labels,predicted)),
                routing_label_n=len(truth_labels), n_questions=len(subset),
                strict_accuracy=float(np.mean(strict_values)) if strict_values else None,
                strict_n=len(strict_values), mean_latency_s=float(np.mean(elapsed)),
                always_hybrid_mean_latency_s=float(np.mean(always)),
                escalation_rate=float(np.mean([t["fallback_used"] for t in current_traces])),
                router_errors=sum(bool(t.get("router_error")) for t in current_traces),
                **{"route_recall_"+route: float(v) for route,v in zip(ROUTES,route_recalls)},
                **{"route_support_"+route: truth_labels.count(route) for route in ROUTES})
            candidates.append(candidate)
    write_csv(output/"threshold_sweep.csv",candidates)
    write_csv(output/"oof_decisions.csv",traces)
    feasible=[c for c in candidates if c["routing_regret"]<=policy["maximum_mean_regret"]]
    if not feasible:
        raise RuntimeError("No candidate meets the predeclared regret constraint; no router frozen")
    best=sorted(feasible,key=lambda c:(-c["latency_savings_s"],-c["macro_f1"],policy["variants"].index(c["variant"]),c["tau"]))[0]
    usable=[i for i in range(len(questions)) if labels[i] in ROUTES]
    artifact=train_artifact(best["variant"],[features[i] for i in usable],[embeddings[i] for i in usable],[labels[i] for i in usable]) if best["variant"] in {"knn","logistic"} else None
    config=dict(selected=True,**best,artifact=artifact,knn_k=policy["knn_k"],llm_model=llm.model, llm_provider="gemini", seed=policy["seed"],
        minimum_vector_score=policy["minimum_vector_score"],
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        mode="no-templates", template_shortcuts=False,
        tuning_split_sha256=sha256(benchmark),policy_sha256=sha256(policy_path),catalog_fingerprint=catalog.fingerprint,
        feature_names=list(FEATURES),exemplars=EXEMPLARS)
    path=output/"frozen_router.json"
    if path.exists():
        raise RuntimeError("Frozen config already exists; do not overwrite")
    raw=(json.dumps(config,indent=2)+"\n").encode()
    path.write_bytes(raw)
    path.with_suffix(".sha256").write_text(hashlib.sha256(raw).hexdigest()+"\n")


if __name__ == "__main__":
    main()

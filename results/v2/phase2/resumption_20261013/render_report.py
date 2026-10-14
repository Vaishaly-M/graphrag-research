"""Render Phase 2 status/results without model calls or held-out data access."""
import json,sys,csv
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[4]))
from src.common import read_jsonl
from scripts.derive_oracle_routes import active_records
from scripts.measure_phase2_routes import usable_timing, measured_oracle, failure_class
OUT=Path(__file__).parent
ROOT=OUT.parents[3]
def table(headers, rows):
    return "\n".join(["| "+" | ".join(headers)+" |","| "+" | ".join("---" for _ in headers)+" |"]+["| "+" | ".join(str(v).replace("|","\\|").replace("\n"," ") for v in r)+" |" for r in rows])+"\n\n"
def csvrows(path):
    with path.open(encoding="utf-8-sig",newline="") as f: return list(csv.DictReader(f))
def main():
    records=active_records(read_jsonl(OUT/"route_outcomes/outcomes.jsonl"))
    groups={}
    for r in records: groups.setdefault(r["question_id"],[]).append(r)
    complete={q:rs for q,rs in groups.items() if len(rs)==3 and all(usable_timing(r) for r in rs)}
    selected=[r for rs in complete.values() for r in rs]
    oracle=measured_oracle(selected)
    progress=json.loads((OUT/"route_outcomes/progress.json").read_text())
    text=["# Phase 2 — no-templates router selection\n\nDate: 2026-10-13 (Asia/Colombo).\n\n",
        f"Route measurement status: **{progress['status']}**. **{len(complete)}/140** questions have all three usable route outcomes. ",
        "No Phase 3 work or held-out answer evaluation was performed. Gold and split contents are unchanged.\n\n",
        "## Protocol and post-hoc amendment\n\n",
        "The user selected no-templates with fresh uncached route measurements. The accepted 140-question Phase 1C split is preserved, with 20 questions per category, six repositories including Airflow, and its documented post-hoc detectable-subject audit. SHA-256: `b46e373f1b9ac2ce3a868ca62cab09589f0540cac6089f713c493fd083d634f6`.\n\n",
        "After 33 outcomes, hybrid generated invalid `ENDS_WITH` for `router-tuning-196f6b2ad2abeb00`. The old all-clean policy stopped collection. On 2026-10-13 the user explicitly authorized a **post-hoc policy amendment**: retain genuine system errors as incorrect and include their execution cost; retry only infrastructure failures. The original error and all 33 original outcomes are preserved. Unknown failures stop for classification. No resampling until a model error disappears.\n\n",
        "The amended oracle chooses minimum measured latency among non-error correct routes; exact ties use graph, vector, hybrid. This differs from Phase 1C's ordinal cost policy. Errors cannot become correct oracle labels. All questions, including no-correct-route questions, remain in accuracy/regret denominators.\n\n",
        "No registered templates or deterministic answers; identical generator, evidence budgets and answer prompt across forced routes; cross-route fallback disabled during collection. Pacing/backoff are excluded from latency. Cache hits and infrastructure-contaminated outcomes cannot supply selection timings. Every route is checkpointed with an append-only attempt journal.\n\n",
        "The outside-sandbox preflight passed: populated Neo4j, verified non-diagnostic index, and local `qwen2.5:7b`. The user subsequently confirmed **Gemini for the LLM router**, matching the Phase 2 brief. The CV script uses Gemini and caches router responses; Ollama is not the selected router provider. An earlier local router smoke test overlapped early route collection: timings are single-run observations on a shared workstation, not isolated performance benchmarks.\n\n",
        "The first full suite passed 65 tests. After the amendment, seven measurement tests passed, including three new cases for error retention, infrastructure classification and unknown failures. Original and amended policies/snapshots are preserved. See [protocol](../results/v2/phase2/resumption_20261013/protocol.md) and [selection rule](../results/v2/phase2/resumption_20261013/selection_rule.json).\n\n",
        "## Route outcomes\n\n",
        "Tables below use only questions with all three policy-usable routes. Partial rows and all attempts remain in the raw journals; incomplete coverage is not a full-split result. Strict accuracy is restricted to `gold_complete=true`.\n\n"]
    rows=[]
    for cat in ["ALL"]+sorted({r["category"] for r in selected}):
        for route in ["graph","vector","hybrid"]:
            rs=[r for r in selected if r["route"]==route and (cat=="ALL" or r["category"]==cat)]
            if not rs: continue
            strict=[r for r in rs if r["gold_complete"] is True]
            rows.append([cat,route,len(rs),f"{sum(r['recall_accuracy'] or 0 for r in rs)/len(rs):.4f}",f"{sum(r['strict_accuracy'] or 0 for r in strict)/len(strict):.4f}" if strict else "N/A",len(strict),sum(r["is_error"] for r in rs),f"{sum(r['latency_s'] for r in rs)/len(rs):.3f}"])
    text.append(table(["Category","Route","n","Recall","Strict","Strict n","Errors","Mean execution seconds"],rows))
    counts=Counter(r["oracle_route"] or "none" for r in oracle)
    text.append(table(["Measured cheapest-correct route","Questions"],[(r,counts[r]) for r in ['graph','vector','hybrid','none']]))
    text.append(table(["Recorded failure class (all active rows)","Outcomes"],sorted(Counter(failure_class(r) for r in records).items())))
    infrastructure=[r for r in records if failure_class(r)=='infrastructure']
    if infrastructure:
        text.append("### Infrastructure interruption\n\nThe continuation stopped on provider/transport failure. Affected timings are excluded from oracle selection. The append-only history preserves failed attempts; previously usable outcomes are not rerun.\n\n")
        text.append(table(["Question", "Route", "Attempt", "Error", "Provider status codes"],
            [[r['question_id'],r['route'],r.get('attempt_number'),r.get('error_type'),
              sorted({str(e.get('provider_status_code')) for e in r.get('retry_events',[]) if e.get('status')=='error'})]
             for r in infrastructure]))
    text.append("## Selection and freezing\n\n")
    if (OUT/"threshold_sweep.csv").exists():
        rows=csvrows(OUT/"threshold_sweep.csv")
        headers=list(rows[0])
        text.append(table(headers,[[r[h] for h in headers] for r in rows]))
    else:
        text.append("Cross-validation and threshold sweep are not yet available. The unchanged selection priorities maximize estimated latency savings subject to mean recall regret <=0.02, then macro-F1, simpler variant, and lower tau. No missing result is treated as zero.\n\n")
    if (OUT/"frozen_router.json").exists():
        text.append("Selected configuration: `results/v2/phase2/resumption_20261013/frozen_router.json` with checksum.\n\n")
    else:
        text.append("**No router is frozen.** Live old-adaptive/new-router comparison is not yet available.\n\n")
    if infrastructure:
        text.append("**Phase 2 is incomplete and stopped on infrastructure failure.** Two continuation attempts at the pending hybrid measurement encountered Gemini 503/504 errors. Neither attempt supplies a usable selection timing. No model switch, timeout change or gold change was made. Resume only after provider availability recovers using `python -B scripts/measure_phase2_routes.py`; the checkpoint skips usable outcomes. No background measurement process remains running at this handoff.\n\n")
        text.append("Pending work: finish route measurements; run Gemini-router five-fold CV and the offline threshold sweep; produce variant comparisons and misrouted examples; integrate and test the selected configuration and held-out frozen-config guard; run the old/new live tuning-only comparison if selection succeeds. The deployment loader's existing Ollama branch also needs Gemini support before deploying an LLM selection. No selected YAML or completed freeze is claimed.\n\n")
        text.append("Continuation verification: seven measurement-policy tests and ten router tests passed with Python unittest (17 total). These cover the current components, not the pending deployment integration. Pytest was unavailable; no package installation was needed.\n\n")
    text.append("## Files and reproducibility\n\n")
    for name in ["src/llm.py","tests/test_llm_retry_status.py","docs/router_selection_rule.md","scripts/measure_phase2_routes.py","tests/test_phase2_measurements.py","reports/phase2.md","results/v2/phase2/resumption_20261013/selection_rule.json","results/v2/phase2/resumption_20261013/train_current.py","results/v2/phase2/resumption_20261013/render_report.py","results/v2/phase2/resumption_20261013/check_local_router.py","results/v2/phase2/resumption_20261013/check_provider.py"]:
        text.append("- `"+name+"`\n")
    text.append("\nAll generated measurements, logs, snapshots, tests, catalog provenance and prior documents are under `results/v2/phase2/resumption_20261013/`. Files contain complete contents, not diffs. No redundant ZIP archive is created.\n")
    health_path=OUT/'provider_recovery/health.json'
    if health_path.exists():
        health=json.loads(health_path.read_text())
        text.append("\n## Blocker repair — 2026-10-13\n\nThe user requested a blocker fix. A minimal non-benchmark prompt (`Reply with OK.`) also returned HTTP 504, showing that the observed failure does not depend on repository retrieval or a large evidence prompt. Google documents 503 as service unavailability and 504 as a deadline failure: [official troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting). This identifies the failure class, not the underlying cause inside Google's service.\n\n")
        text.append("The local retry classifier depended on English message text and did not recognize numeric 504 with `DEADLINE_EXCEEDED`. It now treats explicit HTTP 408/429/500/502/503/504 as retryable, keeps nonretryable HTTP statuses terminal, and retains the existing six-attempt cap, backoff accounting, timeout, model and generation parameters. Six new tests, ten harness tests and seven measurement-policy tests passed (23 total).\n\n")
        text.append("This is a disclosed transport-handling amendment, not a change to answering or scoring. Original complete source files are preserved in `provider_recovery/before_fix/`. Future measurement snapshots use `route_outcomes/transport_fix_v1/`, binding the previous `policy_v2` snapshot by hash; old snapshots and outcomes remain intact. Infrastructure-contaminated timings remain ineligible even if an in-call retry succeeds.\n\n")
        text.append("Latest isolated health result: `"+json.dumps(health)+"`. Diagnostic attempts are stored separately in `provider_recovery/events.jsonl` and are not evaluation rows. A retry repair cannot restore an unavailable upstream service; no successful recovery is claimed unless the health result and subsequent benchmark call succeed.\n")
    (ROOT/"reports/phase2.md").write_text("".join(text),encoding="utf-8")
    print("Report updated:",progress['status'],len(complete),"complete questions")
if __name__=="__main__": main()

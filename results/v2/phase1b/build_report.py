"""Render Phase 1B evidence without running any evaluation or accessing held-out rows."""
import csv
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results/v2/phase1b"
RUN = OUT / "route_outcomes"


def read(path):
    csv.field_size_limit(100_000_000)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"] +
                     ["| " + " | ".join(str(x).replace("|", "\\|") for x in row) + " |" for row in rows]) + "\n\n"


def pct(v):
    return f"{100*float(v):.2f}%" if v != "" and v is not None else "N/A"


def main():
    audit = json.loads((OUT / "disjointness.json").read_text())
    diag = json.loads((OUT / "diagnostic_summary.json").read_text())
    env = json.loads((OUT / "environment_network_current.json").read_text())
    progress = json.loads((RUN / "progress.json").read_text())
    config = json.loads((RUN / "config_snapshot.json").read_text())
    flips = read(OUT / "diagnostic_25_flips.csv")
    nulls = read(OUT / "gold_complete_null.csv")
    summary = read(RUN / "route_summary.csv")
    distributions = read(RUN / "oracle_distribution.csv")
    outcome_rows = [json.loads(line) for line in (RUN / "outcomes.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    active = {(r["question_id"],r["route"]):r for r in outcome_rows}
    pairs = [(r,active[(q,"hybrid")]) for (q,route),r in active.items() if route == "graph" and (q,"hybrid") in active]
    complete = progress["questions_with_all_routes"]
    status = progress["status"]
    lines = ["# Phase 1B — diagnostic route outcomes\n\nDate: 2026-10-12 (Asia/Colombo).\n\n",
             f"**Execution status: {status}. {complete}/70 questions have all three route outcomes; "
             f"{progress['active_errors']} active route errors. Primary-entity disjointness: FAIL.**\n\n",
             "The user explicitly authorized overlap-contaminated diagnostics and transmission of router-tuning "
             "questions and retrieved repository evidence to the configured Gemini API. No Phase 2 training, "
             "selection or freezing was performed. Hidden-test and human-test were not evaluated or modified; "
             "their metadata was read only for the requested exclusion check. No gold was edited. "
             "The old report is preserved byte-for-byte as [phase1b_blocked_2026-10-08.md](phase1b_blocked_2026-10-08.md).\n\n",
             "## Step status\n\n",
             table(["Step", "Status"], [["Environment", "PASS outside network sandbox"],
                 ["0 / Part A", "Verified existing metric code/tests; completed docs and missing 25-flip diagnostic fields"],
                 ["0 / Part B", "Existing split preserved; README/manifest updated; primary-entity disjointness FAIL disclosed"],
                 ["1 / Part C", status], ["2 / Report", "Written with complete-file archive"]]),
             "## Environment and frozen run settings\n\n",
             "Neo4j verification returned these label counts (label counts are not necessarily distinct-node totals):\n\n",
             table(["Label", "Count"], [[r["label"], r["n"]] for r in env["neo4j"]["label_counts"]]),
             "The vector manifest hashes match and `diagnostic_only=false`. Ollama contains `qwen2.5:7b`; "
             "the route experiment uses Gemini. The initial sandbox connectivity failure and successful "
             "network verification are both retained.\n\n",
             table(["Setting", "Value"], [["Generator", config["model_name"]], ["Answer temperature", config["temperature"]],
                 ["Answer token limit", config["config"]["llm"]["max_output_tokens_answer"]],
                 ["Cypher token limit", config["config"]["llm"]["max_output_tokens_cypher"]],
                 ["Gemini RPM", config["rpm"]], ["Application retry budget", config["retry_settings"]["retries"]],
                 ["Vector k", config["k"]], ["Chunk size / overlap", f"{config['chunk_size']} / {config['chunk_overlap']} characters"],
                 ["Route cost order", "graph < vector < hybrid"], ["Graph templates", "Enabled, production behavior"],
                 ["Cross-route safety fallback", "Disabled; graph's own Cypher-generation fallback retained"],
                 ["Cache", "Shared across routes; key = model + generation parameters + prompt SHA-256"],
                 ["Snapshot", "results/v2/phase1b/route_outcomes/config_snapshot.json"]]),
             "The snapshot includes the entire experiment config, source hashes, split and index hashes, model alias, "
             "retry settings and protocol. The model alias is not an immutable provider revision.\n\n",
             "## Step 0 / Part A — existing diagnostic extended\n\n",
             f"The existing adaptive diagnostic has {diag['original_flips']} legacy-to-strict flips (the larger saved "
             "changed-verdict file contains 114 rows across systems/ablations). This extension uses its saved "
             "predicted entities and original generation-query provenance; it does not rerun a held-out evaluation.\n\n",
             table(["Interpretation", "Remaining flips"], [["Strict against unchanged frozen gold", diag["strict_flips_remaining"]],
                 ["Strict, known-complete gold subset", diag["known_complete_flips_remaining"]],
                 ["Recall accuracy", diag["recall_flips_remaining"]],
                 ["Unknown completeness, excluded from strict-complete subset", diag["unknown_completeness"]]]),
             "Unknown completeness is N/A for strict-complete accuracy, never a pass. Extra entities are not "
             "verified as true. Returned length counts extracted entities, not answer lines or tokens. "
             "The complete extra-entity lists are in [diagnostic_25_flips.csv](../results/v2/phase1b/diagnostic_25_flips.csv).\n\n",
             table(["Question", "Gold length", "Returned length", "gold_complete", "Extra entities (count)", "Recall", "Strict"],
                 [[r["question_id"],r["gold_length"],r["returned_length"],r["gold_complete"] or "null",r["extra_entity_count"],
                   r["recall_accuracy"],r["strict_accuracy"]] for r in flips]),
             "Questions with null `gold_complete` are listed below and in "
             "[gold_complete_null.csv](../results/v2/phase1b/gold_complete_null.csv). These lists cover the "
             "requested 25-flip diagnostic and router-tuning, not a new assessment of held-out splits.\n\n"]
    for scope in ("historical_25_flips", "router-tuning"):
        subset = [r for r in nulls if r["scope"] == scope]
        lines += [f"**{scope}: {len(subset)} questions.**\n\n",
                  table(["Question", "Reason"], [[r["question_id"],r["reason"]] for r in subset])]
    lines += ["## Step 0 / Part B — frozen split and exclusion audit\n\n",
              "The existing 70 questions were retained; none were regenerated. New generation seed: `20261009` "
              "(original benchmark: `42`). Tuning-only SHA-256: `"+audit["hashes"]["router-tuning"]+"`.\n\n",
              table(["Category", "Questions"], sorted(audit["categories"].items())),
              table(["Repository", "Questions"], sorted(audit["repositories"].items())),
              "No category is missing. `apache/airflow` is absent by the existing generation policy.\n\n",
              table(["Compared split", "Normalized text overlaps", "Primary-subject overlap pairs", "Result"],
                    [[name,c["text_overlaps"],c["primary_entity_overlaps"],c["status"]] for name,c in audit["checks"].items()]),
              "The audit exits 1 on detected overlap. It checks repository-scoped query subjects rather than "
              "whole expected-answer sets. Code/doc fragments use file identities; a generic keyword is not an "
              "entity. For repository-wide questions, the repository itself is the primary subject. Human "
              "questions have no subject annotations, so zero literal matches cannot prove semantic disjointness.\n\n",
              table(["Tuning question", "Other split / question", "Subject type", "Subject"],
                    [[r["question_id"],name+" / "+str(r["other_question_id"]),r.get("entity_type","text"),r.get("entity") or "text"]
                     for name,c in audit["checks"].items() for r in c["overlaps"]]),
              "The original generator excluded equal complete answer sets, which did not prevent these overlaps. "
              "The README and manifest now disclose tuning-only diagnostic use and failed primary-entity "
              "disjointness. User authorization permits the diagnostic run; it does not make the split disjoint.\n\n",
              "## Step 1 / Part C — route outcomes\n\n",
              "The runner forces each route through the existing production retrieval and answering implementation "
              "(`adaptive_hybrid_graphrag_v2.System`, inherited graph retrieval, shared vector search/fusion and "
              "grounded answering). It does not train or select RouterV2. Templates are enabled for graph access; "
              "these measurements therefore do not isolate routing from template-answer access.\n\n",
              "Each route outcome is appended before proceeding, and CSV/progress files are checkpointed after "
              "every route, hence every question. All API attempts and question-route starts/completions are "
              "logged under the run directory. Errors count as incorrect. Quota errors retain their failed "
              "attempt, stop the run after the existing retry budget, and are retried on a later invocation; "
              "other completed errors remain in the denominator. Earlier attempts are retained.\n\n",
              "The oracle chooses the first recall-correct route in `graph < vector < hybrid`; measured latency "
              "does not choose the label. `oracle_best_accuracy` and `oracle_best_strict_accuracy` are separate "
              "per-question maxima. An oracle requires all three routes for that question. `no_route_correct` "
              "means none was recall-correct. Pacing and backoff are subtracted from per-route latency. Cached "
              "and failed/retried rows are excluded from the clean latency mean; counts disclose the denominator.\n\n",
              table(["Route", "Attempted questions", "Recall accuracy", "Strict accuracy", "Errors", "Clean latency (s)", "Clean n"],
                    [[r["route"],r["n"],pct(r["recall_accuracy"]),pct(r["strict_accuracy"]),r["errors"],
                      f"{float(r['mean_clean_latency_s']):.3f}" if r["mean_clean_latency_s"] else "N/A",r["clean_latency_n"]]
                     for r in summary if r["category"] == "ALL"]),
              table(["Category", "Complete questions", "Graph cheapest", "Vector cheapest", "Hybrid cheapest", "No route correct"],
                    [[r["category"],r["n"],r["graph"],r["vector"],r["hybrid"],r["none"]] for r in distributions]),
              table(["Category", "Route", "n", "Recall accuracy", "Strict accuracy", "Errors"],
                    [[r["category"],r["route"],r["n"],pct(r["recall_accuracy"]),pct(r["strict_accuracy"]),r["errors"]]
                     for r in summary if r["category"] != "ALL"])]
    overall = distributions[0]
    if int(overall["n"]):
        rate = float(overall["vector_cheapest_rate"])
        lines += [f"Vector is the cheapest correct route on **{overall['vector']}/{overall['n']} ({pct(rate)})** "
                  "complete questions. "+("Vector is almost never best under this ordinal cost rule. " if rate <= .05 else "")+
                  f"No route is correct on **{overall['none']}/{overall['n']}** complete questions. "
                  "Graph wins every graph-correct tie by construction; graph template access and the generated "
                  "question distribution limit any general conclusion about vector retrieval.\n\n"]
    if pairs:
        same = sum(a["answer"] == b["answer"] for a,b in pairs)
        deterministic = sum(a.get("answer_generation_mode") == b.get("answer_generation_mode") == "deterministic_graph" for a,b in pairs)
        lines += [f"Graph and hybrid returned identical answers for **{same}/{len(pairs)}** completed pairs; "
                  f"**{deterministic}/{len(pairs)}** pairs used deterministic graph answering in both routes. "
                  "Hybrid still executed vector retrieval, but the production shortcut chooses graph answers "
                  "when available. This explains the answer/accuracy tie and is not evidence that hybrid "
                  "fusion or an LLM independently reached the same answer.\n\n"]
    if status == "QUOTA_STOP":
        lines += [f"**Provider quota/rate limit exhausted after retries. Stop and resume later.** {complete}/70 "
                  f"questions have all three attempts; {progress['questions_without_errors']} have all routes without "
                  "execution errors. Partial route denominators above differ; no 70-question result is claimed.\n\n",
                  "```powershell\n"+progress["resume_command"]+"\n```\n\n"]
    elif complete != 70:
        lines += ["**Incomplete execution.** Only the attempted/complete-question denominators above apply.\n\n"]
    changed = ["scripts/audit_phase1b.py", "scripts/derive_oracle_routes.py", "src/llm.py", "tests/test_phase1b.py",
               "tests/test_router_v2.py", "docs/metrics.md", "data/benchmark/splits_v2/README.md",
               "data/benchmark/splits_v2/manifest.json", "reports/phase1b.md", "reports/phase1b_blocked_2026-10-08.md"]
    lines += ["## Validation and changed files\n\n",
              "The full local suite passed 53 tests. After adding the provider-quota telemetry test, all five "
              "Phase 1B tests passed (54 distinct tests in total). Logs: `results/v2/phase1b/tests.txt` and "
              "`phase1b_tests.txt`. These test ordinal cost selection, independent oracle maxima, error handling, "
              "partial checkpoints, replacement of quota attempts, entity overlap and quota telemetry.\n\n",
              "Source/documentation files changed in this continuation:\n\n"]
    validation_path = OUT / "validation.json"
    if validation_path.exists():
        validation = json.loads(validation_path.read_text())
        lines[-1] = (table(["Saved-output integrity check", "Result"],
                          [[name,"PASS" if ok else "FAIL"] for name,ok in validation["checks"].items()]) +
                     f"Logged API attempts: {validation['api_attempts']}; cache hits: {validation['cache_hits']}. "
                     "These integrity checks do not override the failed split-disjointness check.\n\n"+
                     "Source/documentation files changed in this continuation:\n\n")
    lines += ["- `"+p+"`\n" for p in changed]
    lines += ["\nGenerated artifacts live under `results/v2/phase1b/`: environment checks, audit/snapshot, "
              "diagnostic tables, null-completeness list, test logs, report renderer, validation, and "
              "`route_outcomes/` (configuration snapshot, response cache, attempt/API logs, outcomes, progress, "
              "oracle tables and per-category summaries). The complete generated-file inventory and hashes "
              "are in `artifact_inventory.json`.\n\n",
              "Complete source, documentation, report and result file contents (not diffs) are supplied in "
              "[phase1b_complete_files.zip](../results/v2/phase1b/phase1b_complete_files.zip). "
              "Gold, all split CSV bytes, the index and historical result files were preserved.\n\n",
              "Stopped at Phase 1B. Awaiting confirmation; do not start Phase 2.\n"]
    (ROOT / "reports/phase1b.md").write_text("".join(lines), encoding="utf-8")
    inventory = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in OUT.rglob("*") if p.is_file() and p.name not in {"artifact_inventory.json", "phase1b_complete_files.zip"}}
    (OUT / "artifact_inventory.json").write_text(json.dumps(inventory, indent=2)+"\n", encoding="utf-8")
    with zipfile.ZipFile(OUT / "phase1b_complete_files.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in changed + sorted(inventory) + ["results/v2/phase1b/artifact_inventory.json"]:
            bundle.write(ROOT / name, name)
    print(status, "report and complete-files archive written")


if __name__ == "__main__":
    main()

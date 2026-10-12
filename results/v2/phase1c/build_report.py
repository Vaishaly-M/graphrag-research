"""Render the final Phase 1C report and complete-file archive from saved artifacts only."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/"results/v2/phase1c"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path):
    csv.field_size_limit(100_000_000)
    with path.open(encoding="utf-8-sig",newline="") as stream:
        return list(csv.DictReader(stream))


def table(headers,data):
    return "\n".join(["| "+" | ".join(headers)+" |","| "+" | ".join("---" for _ in headers)+" |"]+
        ["| "+" | ".join(str(v).replace("|","\\|").replace("\n"," ") for v in row)+" |" for row in data])+"\n\n"


def pct(value):
    return "N/A" if value in (None,"") else f"{100*float(value):.2f}%"


def main():
    final=load(OUT/"split_generation/final.json")
    validation=load(OUT/"validation.json")
    pre,post=load(OUT/"v1_reaudit.json"),load(OUT/"disjointness.json")
    modes=validation["modes"]
    complete=all(m.get("status","").startswith("COMPLETE") for m in modes.values())
    lines=["# Phase 1C — template-controlled routing diagnostic\n\nReport completed: 2026-10-13 (Asia/Colombo). Rule change and route execution: 2026-10-12.\n\n",
        "**"+("Both route modes completed." if complete else "Route execution is incomplete; see checkpoint status below.")+"** "
        "The audit rule was changed **post hoc**, after Phase 1B failed, at the user's explicit request. "
        "Results remain tuning diagnostics, not paper/held-out results. No Phase 2 training, selection or "
        "freezing was performed. No hidden-test or human-test answers were evaluated.\n\n",
        "## Status of requested tasks\n\n",
        table(["Task","Status"],[["1 / Subject audit","Revised rule documented; one overlapping v1 question removed; old audit preserved"],
            ["2 / Enlargement",f"{final['count']} questions; 20 per category; six repositories including Airflow"],
            ["3 / No-templates","Implemented and tested; no query lookup or deterministic answering shortcut"],
            ["4 / With-templates",modes["with_templates"]["status"]],["4 / No-templates",modes["no_templates"]["status"]],
            ["5 / Human template rate","Text-only descriptive check completed; no scoring/model calls"],
            ["6 / Five flips","Current-graph exact-fragment inspection completed; gold unchanged"]]),
        "## 1. Post-hoc primary-subject rule\n\n",
        "Changed on **2026-10-12**, after the first audit failed. Repository sharing is intentional and a "
        "repository alone is no longer a primary subject. The primary subjects are commit hash, issue number, "
        "PR number, file path, developer identity and code/doc fragment. Directories alone and generic "
        "issue-search keywords are not subjects. Issue-title lookups use the generated numeric issue identity; "
        "code/doc questions use the actual fragment rather than the returned file.\n\n",
        "File paths, issue/PR numbers and fragments are repository-scoped; commits and developers are global. "
        "Comparison uses casefold/whitespace normalization, normalized path slashes and commit-prefix matches "
        "of at least seven characters. Human questions have no subject annotations, so this detects literal "
        "subject overlap without proving semantic or paraphrase disjointness. The exact rule is recorded in "
        "the script, manifest and [split README](../data/benchmark/splits_v2/README.md).\n\n",
        "The original [Phase 1B audit](../results/v2/phase1b/disjointness.json) and its source snapshot are preserved. "
        "The corrected v1 check still fails for exactly one question:\n\n",
        table(["Tuning question","Other split / question","Primary subject"],
            [[r["question_id"],name+" / "+r["other_question_id"],r.get("entity","")]
             for name,c in pre["checks"].items() for r in c["overlaps"]]),
        table(["Compared split","v1 text / subject overlap pairs","v2 text / subject overlap pairs","v2 result"],
            [[n,f"{pre['checks'][n]['text_overlaps']} / {pre['checks'][n]['primary_entity_overlaps']}",
                f"{c['text_overlaps']} / {c['primary_entity_overlaps']}",c["status"]] for n,c in post["checks"].items()]),
        "Only `router-tuning-c6dc0e1b1b05a2df` was removed. The other 69 v1 rows, including their gold and "
        "metadata, were preserved. `router-tuning_v1.csv` retains the original bytes. No other split was changed.\n\n",
        "## 2. Enlarged tuning-only split\n\n",
        f"Retained **{final['retained']}**, added **{final['added']}**, final **{final['count']}**. New generation seed: "
        "`20261012`; retained v1 seed: `20261009`. Original benchmark seed: `42`.\n\n",
        "v1 SHA-256: `fee8bab59925109abfff7d7b579fa1df92800962403200116fd329f2ce539aa8`.\n\n",
        f"v2 SHA-256: `{final['sha256']}`.\n\n",
        table(["Category","Final questions","Candidate attempts"],[[c,n,final["attempts"][c]] for c,n in sorted(final["categories"].items())]),
        table(["Repository","Final questions"],sorted(final["repositories"].items())),
        "Airflow was included. Its old exclusion was in the prior generation policy/script; the generator "
        "supports repository-scoped Airflow sampling. The user explicitly requested inclusion where possible. "
        "All seven category targets were reached; there is no disjointness-limited shortfall. The recorded "
        "search ceiling was 600 candidate attempts per category. **No exhaustive maximum is claimed**: "
        "generation stopped at the requested 20 per category. Counts above establish feasibility, not a "
        "mathematical maximum. Candidate rejections and resumable RNG state are saved in the generation checkpoint.\n\n",
        "A retained-list aliasing bug initially affected only the generated summary's retained/added counts. "
        "Those metadata counts were corrected to 69/71 after checking every retained row; the split bytes "
        "and gold were unaffected. The original generation snapshot and metadata correction record are both retained.\n\n",
        "A subsequent consistency check canonicalized structured `repo:commit:hash` IDs to their hash before "
        "overlap comparison. Re-auditing v1 and v2 produced the same findings and changed no split rows. "
        "The template run's original source snapshot is preserved under `config_revisions/`; the audit-only "
        "source revision was recorded separately so resumption remains possible. No inference source or "
        "model settings changed during route execution.\n\n",
        "## 3. Shared retrieval and answering protocol\n\n",
        "The prerecord for route execution is [docs/phase1c_protocol.md](../docs/phase1c_protocol.md). "
        "Each run snapshot includes all source/config hashes, split/index hashes, the exact answer prompt, "
        "mode and generation parameters.\n\n"]
    lines.insert(2, "**FAIL: the no-templates experiment completed with 127 network-related route errors (64 graph, 63 hybrid).** "
        "These are counted as incorrect as specified. They comprise 122 DNS lookup failures during Cypher generation, "
        "one unreachable-host failure during Cypher generation, and four Neo4j address-resolution failures. "
        "Only 76/140 questions have error-free outcomes for all three routes. This is an infrastructure-confounded "
        "diagnostic, not a clean test of route quality. The saved failures were not silently discarded or rerun.\n\n")
    config_path=OUT/"with_templates/config_snapshot.json"
    split_rows=rows(ROOT/"data/benchmark/splits_v2/router-tuning.csv")
    repositories=sorted(final["repositories"])
    matrix=Counter((r["category"],r["source_repo"]) for r in split_rows)
    insertion=next(i for i,s in enumerate(lines) if s.startswith("## 3."))
    lines[insertion:insertion]=["Category-by-repository coverage is shown explicitly below; coverage of all six "
        "repositories overall does not imply every category/repository cell is populated.\n\n",
        table(["Category"]+repositories,[[c]+[matrix[c,r] for r in repositories] for c in sorted(final["categories"])])]
    config=load(config_path)
    lines += [table(["Setting","All three routes"],[["Generator",config["model_name"]],
        ["Final answer prompt","ADAPTIVE_FINAL_ANSWER (exact text in snapshot)"],
        ["Answer temperature / max output tokens",f"{config['answer_temperature']} / {config['answer_max_output_tokens']}"],
        ["Final evidence budget",f"{config['evidence_budget']['max_final_items']} items"],
        ["Independent context-token cap","None in the existing code; no token-budget-matching claim"],
        ["Retrieval limits","100 graph rows; vector k=10"],["Fusion weights","0.72 retrieval / 0.20 lexical / 0.08 graph bonus"],
        ["Cypher generation","Same Gemini model; temperature 0; 700 output tokens; read-only and evidence validation"],
        ["Pacing / retries",f"{config['rpm']} RPM; {config['retry_settings']['retries']} application attempts; SDK attempts=1"],
        ["Cross-route safety fallback","Disabled"],["Oracle cost order","graph < vector < hybrid"]]),
        "With-templates preserves the existing registered-query/deterministic-answer behavior. Its shortcut "
        "can directly answer from validated graph rows; the 16-item LLM evidence limit applies when synthesis "
        "is used. This asymmetry is the component being measured, not removed from that track.\n\n",
        "No-templates never calls registered-template lookup or deterministic graph-answer extraction. Graph "
        "uses schema-prompted LLM text-to-Cypher and LLM answering from validated rows. Vector answers from "
        "vector evidence. Hybrid fuses both sources and synthesizes with the same prompt; an `answer` column "
        "cannot trigger a shortcut. Empty evidence uses the existing explicit abstention for every route.\n\n",
        "The response cache is shared by model, parameters and prompt SHA-256. Matching vector and Cypher "
        "calls can therefore be reused across modes/routes. All latencies subtract pacing/backoff; clean "
        "latency means exclude cache-hit, error and retried rows and show their sample count. **N/A is not "
        "zero latency.** The 207 imported template-enabled outcomes retain original Phase 1B timings, "
        "not newly measured times. Every route is journalled/checkpointed, so every question is saved.\n\n",
        "The configured model name is a provider alias, not an immutable model revision. Reusing v1 "
        "responses is explicitly requested here; those responses are not contemporaneous new samples.\n\n",
        "Recall accuracy includes execution errors as incorrect. Main strict accuracy is reported **only "
        "for `gold_complete=true`**; other per-question strict values and strict oracle maxima are N/A. "
        "The raw frozen-set strict value is retained separately for audit. The oracle chooses the first "
        "recall-correct route in the declared cost order, with separate best recall/strict maxima.\n\n",
        "## 4. Both-mode results and routing verdict\n\n"]
    for name,label in (("with_templates","With templates"),("no_templates","No templates")):
        data=modes[name]
        lines += [f"### {label}\n\n",f"Status: **{data['status']}**.\n\n"]
        if "progress" not in data:
            lines += ["No outcomes are available; nothing is scored as zero.\n\n"]
            continue
        progress=data["progress"]
        lines += [f"Complete questions: **{data['complete_questions']}/140**; active route errors: "
                  f"**{progress['active_errors']}**; imported outcomes: **{data['imported_outcomes']}**. "
                  f"New physical API attempts: **{data['local_api_attempts']}**; cache hits: **{data['local_cache_hits']}**.\n\n"]
        summary=rows(OUT/name/"route_summary.csv")
        distribution=rows(OUT/name/"oracle_distribution.csv")
        lines += [table(["Route","n","Recall accuracy","Strict accuracy (complete gold)","Strict n","Errors","Clean latency s","Clean n"],
            [[r["route"],r["n"],pct(r["recall_accuracy"]),pct(r["strict_accuracy"]),r["n_gold_complete"],r["errors"],
              f"{float(r['mean_clean_latency_s']):.3f}" if r["mean_clean_latency_s"] else "N/A",r["clean_latency_n"]]
             for r in summary if r["category"]=="ALL"]),
            f"Oracle best recall accuracy: **{pct(data['oracle_recall_accuracy'])}**; oracle best strict "
            f"accuracy on complete gold: **{pct(data['oracle_strict_accuracy'])}**.\n\n",
            table(["Category","Complete n","Graph cheapest","Vector cheapest","Hybrid cheapest","No route correct"],
                [[r["category"],r["n"],r["graph"],r["vector"],r["hybrid"],r["none"]] for r in distribution]),
            table(["Category","Route","n","Recall","Strict (complete gold)","Strict n","Errors","Clean latency s / n"],
                [[r["category"],r["route"],r["n"],pct(r["recall_accuracy"]),pct(r["strict_accuracy"]),r["n_gold_complete"],r["errors"],
                  (f"{float(r['mean_clean_latency_s']):.3f}" if r["mean_clean_latency_s"] else "N/A")+" / "+r["clean_latency_n"]]
                 for r in summary if r["category"]!="ALL"]),
            table(["Route diversity measure","Questions"],[["At least two different exact answer strings",data["questions_with_any_different_answers"]],
                ["All three answer strings distinct",data["questions_with_three_distinct_answers"]],
                ["Routes differ in recall correctness",data["questions_with_different_recall_correctness"]],
                ["Routes differ in strict correctness (known-complete gold)",f"{data['questions_with_different_strict_correctness']} / {data['strict_comparison_denominator']}"],
                ["Graph/hybrid exact answer ties",data["graph_hybrid_identical"]],
                ["Recall oracle extra correct questions over best single route",data["oracle_gain_questions"]],
                ["Strict oracle extra correct questions over best single route (complete gold)",data["strict_oracle_gain_questions"]]])]
        if progress["active_errors"]:
            lines += ["**Interpretation limit:** network failures disproportionately affected graph and hybrid. "
                "The routing verdict below describes the recorded error-as-incorrect outcomes only; it cannot "
                "establish route dominance or routing benefit under a working environment. A separately recorded "
                "rerun is needed for that conclusion. Full error counts and onset are in "
                "`results/v2/phase1c/no_templates/error_analysis.json`.\n\n"]
        dominant=data["dominating_routes"]
        if dominant:
            lines += ["**Routing verdict:** "+", ".join(dominant)+" weakly dominates on recall correctness "
                      "on every complete question in this run. The oracle adds no correct answers over the "
                      "best fixed route. There is no demonstrated recall-accuracy benefit from routing on "
                      "these data, although the ordinal cheapest-correct route may vary.\n\n"]
        else:
            lines += [f"**Routing verdict:** no single route dominates every complete question. The oracle "
                      f"gets **{data['oracle_gain_questions']}** more questions correct than the best fixed route. "
                      "There is something for routing to decide on this diagnostic split; this is an upper "
                      "bound, not proof that a learned router can realize the gain.\n\n"]
        lines += ["For strict accuracy on known-complete gold, the per-question dominating routes are "
                  +( ", ".join(data["strict_dominating_routes"]) if data["strict_dominating_routes"] else "none")+
                  f"; the strict oracle gains **{data['strict_oracle_gain_questions']}** questions over the "
                  "best fixed route on that subset.\n\n"]
        if data["status"]=="QUOTA_STOP":
            lines += ["**Quota/rate limit exhausted after the configured retries. Resume later; partial "
                      "denominators above are not 140-question results.**\n\n```powershell\n"+progress["resume_command"]+"\n```\n\n"]
        elif not data["status"].startswith("COMPLETE"):
            lines += ["**Incomplete run: the routing verdict is provisional on completed questions only.**\n\n"]
    lines += ["## 5. Human-test descriptive template-match rate\n\n",
        "Only question text was passed to the unchanged template registry. This is a descriptive yes/no "
        "statistic, with no gold, answer inspection, scoring, model calls or tuning.\n\n",
        table(["Breakdown","Category / repository","n","Matched","Unmatched","Match rate"],
            [[r["group"],r["value"],r["n"],r["matched"],r["unmatched"],pct(r["match_rate"])]
             for r in rows(OUT/"inspection/human_template_summary.csv")]),
        "**0/100 match any registered template.** Under the unchanged registry, all 100 would exercise "
        "the non-template path. This says nothing about their answer accuracy.\n\n",
        "## 6. Five known-complete historical flips — review only\n\n",
        "For each requested question, the query searched all current graph files in its repository for "
        "the **exact original fragment**, with no LIMIT. Each gold file is the sole exact match in the "
        "current graph. Thus these five extra-entity penalties are supported by this inspection; the "
        "gold is the only valid answer under the exact-fragment interpretation and current graph. "
        "This does not prove historical snapshot equivalence. All five remain flagged for user review; "
        "gold was not changed.\n\n"]
    reviews=load(OUT/"inspection/five_flip_review.json")
    lines += [table(["Question","Gold count","Returned count","Exact graph matches","Multiple matching files?","Gold sole valid current match?"],
        [[r["question_id"],len(r["gold"]),len(r["returned_entities"]),len(r["graph_matching_files"]),
          r["graph_fragment_in_multiple_files"],r["gold_is_only_valid_answer_in_current_graph"]] for r in reviews])]
    for review in reviews:
        lines += [f"### {review['question_id']}\n\n",review["question"]+"\n\n",
                  "```json\n"+json.dumps({k:review[k] for k in ("fragment","gold","returned_entities","graph_matching_files",
                     "gold_is_only_valid_answer_in_current_graph","flag_for_user_review")},indent=2)+"\n```\n\n"]
    changed=["scripts/audit_phase1b.py","scripts/prepare_phase1c_tuning.py","scripts/derive_oracle_routes.py",
        "scripts/inspect_phase1c.py","src/systems/adaptive_hybrid_graphrag_v2.py","tests/test_phase1c.py",
        "tests/test_phase1b.py","docs/phase1c_protocol.md","data/benchmark/splits_v2/README.md",
        "data/benchmark/splits_v2/manifest.json","data/benchmark/splits_v2/router-tuning.csv",
        "data/benchmark/splits_v2/router-tuning_v1.csv","reports/phase1c.md"]
    lines += ["## Validation, recovery and changed files\n\n",
        "The full suite passed 60 tests. The seven focused Phase 1C tests then passed after adding the "
        "Windows checkpoint-lock regression test (61 distinct tests in total). Tests cover no template "
        "lookup/shortcut in any route, hybrid synthesis, shared prompt/settings, post-hoc subjects and "
        "strict N/A handling. Logs: `results/v2/phase1c/tests.txt` and `checkpoint_tests.txt`.\n\n",
        "The first template-result import encountered a transient Windows file-replacement denial before "
        "any new model calls. Its partial journal/config are preserved in `with_templates_import_attempt1/`. "
        "A bounded local rename retry was added and the import restarted. No provider request was retried "
        "because of that local failure.\n\n",
        table(["Data integrity check","Result"],[[k,"PASS" if v else "FAIL"] for k,v in validation["checks"].items()]),
        table(["Mode","All available output-integrity checks passed"],[[name,data.get("all_checks_pass","N/A")] for name,data in modes.items()]),
        "Detailed checks and counts are in [validation.json](../results/v2/phase1c/validation.json). "
        "Checkpoints, attempts, response cache, raw answers, generation provenance, snapshots, complete "
        "per-question strict/recall outcomes and oracle tables are under `results/v2/phase1c/`.\n\n",
        "Changed source, documentation and explicitly authorized split files:\n\n"]
    lines += ["- `"+p+"`\n" for p in changed]
    lines += ["\nThe complete generated-file inventory is `results/v2/phase1c/artifact_inventory.json`. "
        "Complete file contents are retained directly in the workspace. The redundant ZIP archive and stale "
        "temporary import checkpoint were removed at the user's request. Prior Phase 1B results and all protected splits remain unchanged.\n\n",
        "Stopped at Phase 1C. Awaiting confirmation; Phase 2 was not started.\n"]
    (ROOT/"reports/phase1c.md").write_text("".join(lines),encoding="utf-8")
    inventory={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.rglob("*")
               if p.is_file() and p.name not in {"artifact_inventory.json","phase1c_complete_files.zip"}}
    (OUT/"artifact_inventory.json").write_text(json.dumps(inventory,indent=2)+"\n",encoding="utf-8")
    print("Phase 1C report and file inventory written")


if __name__=="__main__":
    main()

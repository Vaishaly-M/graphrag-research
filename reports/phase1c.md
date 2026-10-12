# Phase 1C — template-controlled routing diagnostic

Report completed: 2026-10-13 (Asia/Colombo). Rule change and route execution: 2026-10-12.

**Both route modes completed.** The audit rule was changed **post hoc**, after Phase 1B failed, at the user's explicit request. Results remain tuning diagnostics, not paper/held-out results. No Phase 2 training, selection or freezing was performed. No hidden-test or human-test answers were evaluated.

**FAIL: the no-templates experiment completed with 127 network-related route errors (64 graph, 63 hybrid).** These are counted as incorrect as specified. They comprise 122 DNS lookup failures during Cypher generation, one unreachable-host failure during Cypher generation, and four Neo4j address-resolution failures. Only 76/140 questions have error-free outcomes for all three routes. This is an infrastructure-confounded diagnostic, not a clean test of route quality. The saved failures were not silently discarded or rerun.

## Status of requested tasks

| Task | Status |
| --- | --- |
| 1 / Subject audit | Revised rule documented; one overlapping v1 question removed; old audit preserved |
| 2 / Enlargement | 140 questions; 20 per category; six repositories including Airflow |
| 3 / No-templates | Implemented and tested; no query lookup or deterministic answering shortcut |
| 4 / With-templates | COMPLETE_DIAGNOSTIC |
| 4 / No-templates | COMPLETE_WITH_ERRORS_DIAGNOSTIC |
| 5 / Human template rate | Text-only descriptive check completed; no scoring/model calls |
| 6 / Five flips | Current-graph exact-fragment inspection completed; gold unchanged |

## 1. Post-hoc primary-subject rule

Changed on **2026-10-12**, after the first audit failed. Repository sharing is intentional and a repository alone is no longer a primary subject. The primary subjects are commit hash, issue number, PR number, file path, developer identity and code/doc fragment. Directories alone and generic issue-search keywords are not subjects. Issue-title lookups use the generated numeric issue identity; code/doc questions use the actual fragment rather than the returned file.

File paths, issue/PR numbers and fragments are repository-scoped; commits and developers are global. Comparison uses casefold/whitespace normalization, normalized path slashes and commit-prefix matches of at least seven characters. Human questions have no subject annotations, so this detects literal subject overlap without proving semantic or paraphrase disjointness. The exact rule is recorded in the script, manifest and [split README](../data/benchmark/splits_v2/README.md).

The original [Phase 1B audit](../results/v2/phase1b/disjointness.json) and its source snapshot are preserved. The corrected v1 check still fails for exactly one question:

| Tuning question | Other split / question | Primary subject |
| --- | --- | --- |
| router-tuning-c6dc0e1b1b05a2df | development / developer_activity-006 | choonghee.lee@hotmail.com |

| Compared split | v1 text / subject overlap pairs | v2 text / subject overlap pairs | v2 result |
| --- | --- | --- | --- |
| development | 0 / 1 | 0 / 0 | PASS_DETECTABLE_SUBJECTS |
| validation | 0 / 0 | 0 / 0 | PASS_DETECTABLE_SUBJECTS |
| hidden-test | 0 / 0 | 0 / 0 | PASS_DETECTABLE_SUBJECTS |
| human-test | 0 / 0 | 0 / 0 | PASS_DETECTABLE_SUBJECTS |

Only `router-tuning-c6dc0e1b1b05a2df` was removed. The other 69 v1 rows, including their gold and metadata, were preserved. `router-tuning_v1.csv` retains the original bytes. No other split was changed.

## 2. Enlarged tuning-only split

Retained **69**, added **71**, final **140**. New generation seed: `20261012`; retained v1 seed: `20261009`. Original benchmark seed: `42`.

v1 SHA-256: `fee8bab59925109abfff7d7b579fa1df92800962403200116fd329f2ce539aa8`.

v2 SHA-256: `b46e373f1b9ac2ce3a868ca62cab09589f0540cac6089f713c493fd083d634f6`.

| Category | Final questions | Candidate attempts |
| --- | --- | --- |
| code_retrieval | 20 | 84 |
| dependency_analysis | 20 | 10 |
| developer_activity | 20 | 19 |
| documentation_lookup | 20 | 71 |
| issue_pr_analysis | 20 | 15 |
| multi_hop | 20 | 12 |
| structure | 20 | 12 |

| Repository | Final questions |
| --- | --- |
| apache/airflow | 23 |
| dotnet/eShop | 28 |
| mlflow/mlflow | 26 |
| openmrs/openmrs-core | 24 |
| spring-projects/spring-petclinic | 24 |
| synthetic-org/platform | 15 |

Airflow was included. Its old exclusion was in the prior generation policy/script; the generator supports repository-scoped Airflow sampling. The user explicitly requested inclusion where possible. All seven category targets were reached; there is no disjointness-limited shortfall. The recorded search ceiling was 600 candidate attempts per category. **No exhaustive maximum is claimed**: generation stopped at the requested 20 per category. Counts above establish feasibility, not a mathematical maximum. Candidate rejections and resumable RNG state are saved in the generation checkpoint.

A retained-list aliasing bug initially affected only the generated summary's retained/added counts. Those metadata counts were corrected to 69/71 after checking every retained row; the split bytes and gold were unaffected. The original generation snapshot and metadata correction record are both retained.

A subsequent consistency check canonicalized structured `repo:commit:hash` IDs to their hash before overlap comparison. Re-auditing v1 and v2 produced the same findings and changed no split rows. The template run's original source snapshot is preserved under `config_revisions/`; the audit-only source revision was recorded separately so resumption remains possible. No inference source or model settings changed during route execution.

Category-by-repository coverage is shown explicitly below; coverage of all six repositories overall does not imply every category/repository cell is populated.

| Category | apache/airflow | dotnet/eShop | mlflow/mlflow | openmrs/openmrs-core | spring-projects/spring-petclinic | synthetic-org/platform |
| --- | --- | --- | --- | --- | --- | --- |
| code_retrieval | 4 | 4 | 4 | 4 | 4 | 0 |
| dependency_analysis | 4 | 4 | 3 | 3 | 3 | 3 |
| developer_activity | 3 | 3 | 4 | 4 | 3 | 3 |
| documentation_lookup | 3 | 5 | 4 | 4 | 4 | 0 |
| issue_pr_analysis | 3 | 4 | 3 | 3 | 4 | 3 |
| multi_hop | 3 | 4 | 4 | 3 | 3 | 3 |
| structure | 3 | 4 | 4 | 3 | 3 | 3 |

## 3. Shared retrieval and answering protocol

The prerecord for route execution is [docs/phase1c_protocol.md](../docs/phase1c_protocol.md). Each run snapshot includes all source/config hashes, split/index hashes, the exact answer prompt, mode and generation parameters.

| Setting | All three routes |
| --- | --- |
| Generator | gemini-flash-lite-latest |
| Final answer prompt | ADAPTIVE_FINAL_ANSWER (exact text in snapshot) |
| Answer temperature / max output tokens | 0.0 / 1024 |
| Final evidence budget | 16 items |
| Independent context-token cap | None in the existing code; no token-budget-matching claim |
| Retrieval limits | 100 graph rows; vector k=10 |
| Fusion weights | 0.72 retrieval / 0.20 lexical / 0.08 graph bonus |
| Cypher generation | Same Gemini model; temperature 0; 700 output tokens; read-only and evidence validation |
| Pacing / retries | 10 RPM; 6 application attempts; SDK attempts=1 |
| Cross-route safety fallback | Disabled |
| Oracle cost order | graph < vector < hybrid |

With-templates preserves the existing registered-query/deterministic-answer behavior. Its shortcut can directly answer from validated graph rows; the 16-item LLM evidence limit applies when synthesis is used. This asymmetry is the component being measured, not removed from that track.

No-templates never calls registered-template lookup or deterministic graph-answer extraction. Graph uses schema-prompted LLM text-to-Cypher and LLM answering from validated rows. Vector answers from vector evidence. Hybrid fuses both sources and synthesizes with the same prompt; an `answer` column cannot trigger a shortcut. Empty evidence uses the existing explicit abstention for every route.

The response cache is shared by model, parameters and prompt SHA-256. Matching vector and Cypher calls can therefore be reused across modes/routes. All latencies subtract pacing/backoff; clean latency means exclude cache-hit, error and retried rows and show their sample count. **N/A is not zero latency.** The 207 imported template-enabled outcomes retain original Phase 1B timings, not newly measured times. Every route is journalled/checkpointed, so every question is saved.

The configured model name is a provider alias, not an immutable model revision. Reusing v1 responses is explicitly requested here; those responses are not contemporaneous new samples.

Recall accuracy includes execution errors as incorrect. Main strict accuracy is reported **only for `gold_complete=true`**; other per-question strict values and strict oracle maxima are N/A. The raw frozen-set strict value is retained separately for audit. The oracle chooses the first recall-correct route in the declared cost order, with separate best recall/strict maxima.

## 4. Both-mode results and routing verdict

### With templates

Status: **COMPLETE_DIAGNOSTIC**.

Complete questions: **140/140**; active route errors: **0**; imported outcomes: **207**. New physical API attempts: **74**; cache hits: **2**.

| Route | n | Recall accuracy | Strict accuracy (complete gold) | Strict n | Errors | Clean latency s | Clean n |
| --- | --- | --- | --- | --- | --- | --- | --- |
| graph | 140 | 95.71% | 91.15% | 113 | 0 | 0.218 | 140 |
| vector | 140 | 12.86% | 15.93% | 113 | 0 | 3.388 | 139 |
| hybrid | 140 | 95.71% | 91.15% | 113 | 0 | 0.269 | 138 |

Oracle best recall accuracy: **95.71%**; oracle best strict accuracy on complete gold: **92.92%**.

| Category | Complete n | Graph cheapest | Vector cheapest | Hybrid cheapest | No route correct |
| --- | --- | --- | --- | --- | --- |
| ALL | 140 | 134 | 0 | 0 | 6 |
| code_retrieval | 20 | 20 | 0 | 0 | 0 |
| dependency_analysis | 20 | 18 | 0 | 0 | 2 |
| developer_activity | 20 | 17 | 0 | 0 | 3 |
| documentation_lookup | 20 | 20 | 0 | 0 | 0 |
| issue_pr_analysis | 20 | 20 | 0 | 0 | 0 |
| multi_hop | 20 | 19 | 0 | 0 | 1 |
| structure | 20 | 20 | 0 | 0 | 0 |

| Category | Route | n | Recall | Strict (complete gold) | Strict n | Errors | Clean latency s / n |
| --- | --- | --- | --- | --- | --- | --- | --- |
| code_retrieval | graph | 20 | 100.00% | 80.00% | 20 | 0 | 0.152 / 20 |
| code_retrieval | vector | 20 | 20.00% | 20.00% | 20 | 0 | 8.109 / 20 |
| code_retrieval | hybrid | 20 | 100.00% | 80.00% | 20 | 0 | 0.280 / 20 |
| dependency_analysis | graph | 20 | 90.00% | 90.00% | 20 | 0 | 0.681 / 20 |
| dependency_analysis | vector | 20 | 0.00% | 0.00% | 20 | 0 | 3.223 / 19 |
| dependency_analysis | hybrid | 20 | 90.00% | 90.00% | 20 | 0 | 0.245 / 19 |
| developer_activity | graph | 20 | 85.00% | 82.35% | 17 | 0 | 0.178 / 20 |
| developer_activity | vector | 20 | 5.00% | 5.88% | 17 | 0 | 1.385 / 20 |
| developer_activity | hybrid | 20 | 85.00% | 82.35% | 17 | 0 | 0.256 / 19 |
| documentation_lookup | graph | 20 | 100.00% | 95.00% | 20 | 0 | 0.128 / 20 |
| documentation_lookup | vector | 20 | 30.00% | 30.00% | 20 | 0 | 1.610 / 20 |
| documentation_lookup | hybrid | 20 | 100.00% | 95.00% | 20 | 0 | 0.252 / 20 |
| issue_pr_analysis | graph | 20 | 100.00% | 100.00% | 9 | 0 | 0.135 / 20 |
| issue_pr_analysis | vector | 20 | 25.00% | 55.56% | 9 | 0 | 1.351 / 20 |
| issue_pr_analysis | hybrid | 20 | 100.00% | 100.00% | 9 | 0 | 0.266 / 20 |
| multi_hop | graph | 20 | 95.00% | 100.00% | 16 | 0 | 0.123 / 20 |
| multi_hop | vector | 20 | 10.00% | 12.50% | 16 | 0 | 1.431 / 20 |
| multi_hop | hybrid | 20 | 95.00% | 100.00% | 16 | 0 | 0.289 / 20 |
| structure | graph | 20 | 100.00% | 100.00% | 11 | 0 | 0.125 / 20 |
| structure | vector | 20 | 0.00% | 0.00% | 11 | 0 | 6.597 / 20 |
| structure | hybrid | 20 | 100.00% | 100.00% | 11 | 0 | 0.294 / 20 |

| Route diversity measure | Questions |
| --- | --- |
| At least two different exact answer strings | 127 |
| All three answer strings distinct | 0 |
| Routes differ in recall correctness | 116 |
| Routes differ in strict correctness (known-complete gold) | 89 / 113 |
| Graph/hybrid exact answer ties | 140 |
| Recall oracle extra correct questions over best single route | 0 |
| Strict oracle extra correct questions over best single route (complete gold) | 2 |

**Routing verdict:** graph, hybrid weakly dominates on recall correctness on every complete question in this run. The oracle adds no correct answers over the best fixed route. There is no demonstrated recall-accuracy benefit from routing on these data, although the ordinal cheapest-correct route may vary.

For strict accuracy on known-complete gold, the per-question dominating routes are none; the strict oracle gains **2** questions over the best fixed route on that subset.

### No templates

Status: **COMPLETE_WITH_ERRORS_DIAGNOSTIC**.

Complete questions: **140/140**; active route errors: **127**; imported outcomes: **0**. New physical API attempts: **327**; cache hits: **300**.

| Route | n | Recall accuracy | Strict accuracy (complete gold) | Strict n | Errors | Clean latency s | Clean n |
| --- | --- | --- | --- | --- | --- | --- | --- |
| graph | 140 | 18.57% | 22.12% | 113 | 64 | 3.642 | 76 |
| vector | 140 | 12.86% | 15.93% | 113 | 0 | N/A | 0 |
| hybrid | 140 | 10.00% | 12.39% | 113 | 63 | 4.024 | 1 |

Oracle best recall accuracy: **27.14%**; oracle best strict accuracy on complete gold: **32.74%**.

| Category | Complete n | Graph cheapest | Vector cheapest | Hybrid cheapest | No route correct |
| --- | --- | --- | --- | --- | --- |
| ALL | 140 | 26 | 12 | 0 | 102 |
| code_retrieval | 20 | 9 | 2 | 0 | 9 |
| dependency_analysis | 20 | 3 | 0 | 0 | 17 |
| developer_activity | 20 | 0 | 1 | 0 | 19 |
| documentation_lookup | 20 | 7 | 4 | 0 | 9 |
| issue_pr_analysis | 20 | 5 | 3 | 0 | 12 |
| multi_hop | 20 | 2 | 2 | 0 | 16 |
| structure | 20 | 0 | 0 | 0 | 20 |

| Category | Route | n | Recall | Strict (complete gold) | Strict n | Errors | Clean latency s / n |
| --- | --- | --- | --- | --- | --- | --- | --- |
| code_retrieval | graph | 20 | 45.00% | 45.00% | 20 | 10 | 3.630 / 10 |
| code_retrieval | vector | 20 | 20.00% | 20.00% | 20 | 0 | N/A / 0 |
| code_retrieval | hybrid | 20 | 35.00% | 35.00% | 20 | 10 | N/A / 0 |
| dependency_analysis | graph | 20 | 15.00% | 15.00% | 20 | 10 | 3.586 / 10 |
| dependency_analysis | vector | 20 | 0.00% | 0.00% | 20 | 0 | N/A / 0 |
| dependency_analysis | hybrid | 20 | 0.00% | 0.00% | 20 | 10 | N/A / 0 |
| developer_activity | graph | 20 | 0.00% | 0.00% | 17 | 11 | 6.815 / 9 |
| developer_activity | vector | 20 | 5.00% | 5.88% | 17 | 0 | N/A / 0 |
| developer_activity | hybrid | 20 | 0.00% | 0.00% | 17 | 10 | 4.024 / 1 |
| documentation_lookup | graph | 20 | 35.00% | 35.00% | 20 | 10 | 3.605 / 10 |
| documentation_lookup | vector | 20 | 30.00% | 30.00% | 20 | 0 | N/A / 0 |
| documentation_lookup | hybrid | 20 | 15.00% | 15.00% | 20 | 10 | N/A / 0 |
| issue_pr_analysis | graph | 20 | 25.00% | 44.44% | 9 | 11 | 3.507 / 9 |
| issue_pr_analysis | vector | 20 | 25.00% | 55.56% | 9 | 0 | N/A / 0 |
| issue_pr_analysis | hybrid | 20 | 10.00% | 22.22% | 9 | 11 | N/A / 0 |
| multi_hop | graph | 20 | 10.00% | 12.50% | 16 | 1 | 3.020 / 19 |
| multi_hop | vector | 20 | 10.00% | 12.50% | 16 | 0 | N/A / 0 |
| multi_hop | hybrid | 20 | 10.00% | 12.50% | 16 | 1 | N/A / 0 |
| structure | graph | 20 | 0.00% | 0.00% | 11 | 11 | 2.037 / 9 |
| structure | vector | 20 | 0.00% | 0.00% | 11 | 0 | N/A / 0 |
| structure | hybrid | 20 | 0.00% | 0.00% | 11 | 11 | N/A / 0 |

| Route diversity measure | Questions |
| --- | --- |
| At least two different exact answer strings | 101 |
| All three answer strings distinct | 3 |
| Routes differ in recall correctness | 32 |
| Routes differ in strict correctness (known-complete gold) | 31 / 113 |
| Graph/hybrid exact answer ties | 111 |
| Recall oracle extra correct questions over best single route | 12 |
| Strict oracle extra correct questions over best single route (complete gold) | 12 |

**Interpretation limit:** network failures disproportionately affected graph and hybrid. The routing verdict below describes the recorded error-as-incorrect outcomes only; it cannot establish route dominance or routing benefit under a working environment. A separately recorded rerun is needed for that conclusion. Full error counts and onset are in `results/v2/phase1c/no_templates/error_analysis.json`.

**Routing verdict:** no single route dominates every complete question. The oracle gets **12** more questions correct than the best fixed route. There is something for routing to decide on this diagnostic split; this is an upper bound, not proof that a learned router can realize the gain.

For strict accuracy on known-complete gold, the per-question dominating routes are none; the strict oracle gains **12** questions over the best fixed route on that subset.

## 5. Human-test descriptive template-match rate

Only question text was passed to the unchanged template registry. This is a descriptive yes/no statistic, with no gold, answer inspection, scoring, model calls or tuning.

| Breakdown | Category / repository | n | Matched | Unmatched | Match rate |
| --- | --- | --- | --- | --- | --- |
| ALL | ALL | 100 | 0 | 100 | 0.00% |
| category | Code retrieval | 14 | 0 | 14 | 0.00% |
| category | Dependency analysis | 14 | 0 | 14 | 0.00% |
| category | Developer activity | 14 | 0 | 14 | 0.00% |
| category | Documentation lookup | 14 | 0 | 14 | 0.00% |
| category | Issue/PR analysis | 14 | 0 | 14 | 0.00% |
| category | Multi-hop reasoning | 15 | 0 | 15 | 0.00% |
| category | Structure | 15 | 0 | 15 | 0.00% |
| repository | apache/airflow | 20 | 0 | 20 | 0.00% |
| repository | dotnet/eShop | 20 | 0 | 20 | 0.00% |
| repository | mlflow/mlflow | 20 | 0 | 20 | 0.00% |
| repository | openmrs/openmrs-core | 20 | 0 | 20 | 0.00% |
| repository | spring-projects/spring-petclinic | 20 | 0 | 20 | 0.00% |

**0/100 match any registered template.** Under the unchanged registry, all 100 would exercise the non-template path. This says nothing about their answer accuracy.

## 6. Five known-complete historical flips — review only

For each requested question, the query searched all current graph files in its repository for the **exact original fragment**, with no LIMIT. Each gold file is the sole exact match in the current graph. Thus these five extra-entity penalties are supported by this inspection; the gold is the only valid answer under the exact-fragment interpretation and current graph. This does not prove historical snapshot equivalence. All five remain flagged for user review; gold was not changed.

| Question | Gold count | Returned count | Exact graph matches | Multiple matching files? | Gold sole valid current match? |
| --- | --- | --- | --- | --- | --- |
| code_retrieval-003 | 1 | 21 | 1 | False | True |
| code_retrieval-005 | 1 | 74 | 1 | False | True |
| code_retrieval-013 | 1 | 100 | 1 | False | True |
| code_retrieval-018 | 1 | 19 | 1 | False | True |
| code_retrieval-033 | 1 | 4 | 1 | False | True |

### code_retrieval-003

Which source file in repository apache/airflow contains the code fragment "test_app = client(apps="all").app"?

```json
{
  "fragment": "test_app = client(apps=\"all\").app",
  "gold": [
    "airflow-core/tests/unit/api_fastapi/test_app.py"
  ],
  "returned_entities": [
    "airflow-core/src/airflow/api_fastapi/core_api/services/public/task_instances.py",
    "airflow-core/src/airflow/configuration.py",
    "airflow-core/src/airflow/utils/orm_event_handlers.py",
    "airflow-core/tests/unit/api_fastapi/test_app.py",
    "devel-common/src/tests_common/test_utils/perf/perf_kit/sqlalchemy.py",
    "java-sdk/adr/0003-pure-java-dags.md",
    "java-sdk/sdk/src/main/kotlin/org/apache/airflow/sdk/execution/Client.kt",
    "java-sdk/sdk/src/main/kotlin/org/apache/airflow/sdk/execution/Frame.kt",
    "java-sdk/sdk/src/test/kotlin/org/apache/airflow/sdk/ClientTest.kt",
    "java-sdk/sdk/src/test/kotlin/org/apache/airflow/sdk/ContextTest.kt",
    "java-sdk/sdk/src/test/kotlin/org/apache/airflow/sdk/execution/TaskTest.kt",
    "providers/alibaba/src/airflow/providers/alibaba/cloud/hooks/oss.py",
    "providers/common/sql/src/airflow/providers/common/sql/operators/sql.py",
    "providers/fab/src/airflow/providers/fab/auth_manager/api_fastapi/routes/login.py",
    "providers/fab/src/airflow/providers/fab/auth_manager/api_fastapi/services/users.py",
    "providers/fab/src/airflow/providers/fab/www/extensions/init_appbuilder.py",
    "providers/fab/src/airflow/providers/fab/www/static/js/main.js",
    "providers/google/src/airflow/providers/google/cloud/hooks/kubernetes_engine.py",
    "scripts/ci/analyze_ci_job_durations.py",
    "scripts/ci/prek/check_metrics_synced_with_the_registry.py",
    "shared/listeners/src/airflow_shared/listeners/listener.py"
  ],
  "graph_matching_files": [
    "airflow-core/tests/unit/api_fastapi/test_app.py"
  ],
  "gold_is_only_valid_answer_in_current_graph": true,
  "flag_for_user_review": true
}
```

### code_retrieval-005

Which source file in repository apache/airflow contains the code fragment "icon={hideIcon ? undefined : <FiTag data-testid="dag-tag" />}"?

```json
{
  "fragment": "icon={hideIcon ? undefined : <FiTag data-testid=\"dag-tag\" />}",
  "gold": [
    "airflow-core/src/airflow/ui/src/pages/DagsList/DagTags.tsx"
  ],
  "returned_entities": [
    "airflow-core/src/airflow/ui/src/components/AssetExpression/AssetNode.tsx",
    "airflow-core/src/airflow/ui/src/components/Banner/BackfillBanner.tsx",
    "airflow-core/src/airflow/ui/src/components/BreadcrumbStats.tsx",
    "airflow-core/src/airflow/ui/src/components/DagActions/FavoriteDagButton.tsx",
    "airflow-core/src/airflow/ui/src/components/DagRunInfo.tsx",
    "airflow-core/src/airflow/ui/src/components/DagVersion.tsx",
    "airflow-core/src/airflow/ui/src/components/FlexibleForm/FlexibleForm.tsx",
    "airflow-core/src/airflow/ui/src/components/Graph/TaskNode.tsx",
    "airflow-core/src/airflow/ui/src/components/MarkdownModal.tsx",
    "airflow-core/src/airflow/ui/src/components/NeedsReviewButton.tsx",
    "airflow-core/src/airflow/ui/src/components/PresetFiltersMenu.tsx",
    "airflow-core/src/airflow/ui/src/components/SearchBar.tsx",
    "airflow-core/src/airflow/ui/src/components/StateBadge.tsx",
    "airflow-core/src/airflow/ui/src/components/StatsCard.tsx",
    "airflow-core/src/airflow/ui/src/components/TaskName.tsx",
    "airflow-core/src/airflow/ui/src/components/ui/Checkbox.tsx",
    "airflow-core/src/airflow/ui/src/components/ui/Clipboard.tsx",
    "airflow-core/src/airflow/ui/src/components/ui/LazyClipboard.tsx",
    "airflow-core/src/airflow/ui/src/components/ui/RadioCard.tsx",
    "airflow-core/src/airflow/ui/src/components/ui/Toaster/Toaster.tsx",
    "airflow-core/src/airflow/ui/src/layouts/BaseLayout.tsx",
    "airflow-core/src/airflow/ui/src/layouts/Details/DetailsLayout.tsx",
    "airflow-core/src/airflow/ui/src/layouts/Details/Grid/Bar.tsx",
    "airflow-core/src/airflow/ui/src/layouts/Details/PanelButtons.tsx",
    "airflow-core/src/airflow/ui/src/layouts/Nav/NavButton.tsx",
    "airflow-core/src/airflow/ui/src/pages/Asset/Header.tsx",
    "airflow-core/src/airflow/ui/src/pages/AssetsList/AssetsList.tsx",
    "airflow-core/src/airflow/ui/src/pages/Connections/ConnectionStandardFields.tsx",
    "airflow-core/src/airflow/ui/src/pages/Connections/Connections.tsx",
    "airflow-core/src/airflow/ui/src/pages/Dag/Calendar/CalendarCell.tsx",
    "airflow-core/src/airflow/ui/src/pages/Dag/DeadlineAlertsBadge.tsx",
    "airflow-core/src/airflow/ui/src/pages/Dag/Header.tsx",
    "airflow-core/src/airflow/ui/src/pages/Dag/Overview/AllDeadlinesModal.tsx",
    "airflow-core/src/airflow/ui/src/pages/Dag/Overview/DagDeadlines.tsx",
    "airflow-core/src/airflow/ui/src/pages/Dag/Overview/DeadlineRow.tsx",
    "airflow-core/src/airflow/ui/src/pages/Dag/Overview/Overview.tsx",
    "airflow-core/src/airflow/ui/src/pages/DagRuns/DagRuns.tsx",
    "airflow-core/src/airflow/ui/src/pages/DagsList/DagTags.tsx",
    "airflow-core/src/airflow/ui/src/pages/DagsList/DagsFilters/RunStateSelect.tsx",
    "airflow-core/src/airflow/ui/src/pages/DagsList/DagsList.tsx",
    "airflow-core/src/airflow/ui/src/pages/Dashboard/Deadlines/DeadlineSection.tsx",
    "airflow-core/src/airflow/ui/src/pages/Dashboard/Stats/DagImportErrors.tsx",
    "airflow-core/src/airflow/ui/src/pages/Dashboard/Stats/PluginImportErrors.tsx",
    "airflow-core/src/airflow/ui/src/pages/Dashboard/Stats/Stats.tsx",
    "airflow-core/src/airflow/ui/src/pages/Deadlines/index.tsx",
    "airflow-core/src/airflow/ui/src/pages/GroupTaskInstance/GroupTaskInstance.tsx",
    "airflow-core/src/airflow/ui/src/pages/GroupTaskInstance/Header.tsx",
    "airflow-core/src/airflow/ui/src/pages/HITLTaskInstances/HITLTaskInstances.tsx",
    "airflow-core/src/airflow/ui/src/pages/Jobs.tsx",
    "airflow-core/src/airflow/ui/src/pages/MappedTaskInstance/Header.tsx",
    "airflow-core/src/airflow/ui/src/pages/MappedTaskInstance/MappedTaskInstance.tsx",
    "airflow-core/src/airflow/ui/src/pages/Plugins.tsx",
    "airflow-core/src/airflow/ui/src/pages/Pools/PoolBarCard.tsx",
    "airflow-core/src/airflow/ui/src/pages/Providers.tsx",
    "airflow-core/src/airflow/ui/src/pages/ReactPlugin.tsx",
    "airflow-core/src/airflow/ui/src/pages/Run/DeadlineStatus.tsx",
    "airflow-core/src/airflow/ui/src/pages/Run/DeadlineStatusModal.tsx",
    "airflow-core/src/airflow/ui/src/pages/Run/Details.tsx",
    "airflow-core/src/airflow/ui/src/pages/Run/Header.tsx",
    "airflow-core/src/airflow/ui/src/pages/Run/Run.tsx",
    "airflow-core/src/airflow/ui/src/pages/Task/GroupTaskHeader.tsx",
    "airflow-core/src/airflow/ui/src/pages/Task/Header.tsx",
    "airflow-core/src/airflow/ui/src/pages/Task/Task.tsx",
    "airflow-core/src/airflow/ui/src/pages/TaskInstance/Header.tsx",
    "airflow-core/src/airflow/ui/src/pages/TaskInstance/Logs/LogSearchInput.tsx",
    "airflow-core/src/airflow/ui/src/pages/TaskInstance/Logs/ScrollToButton.tsx",
    "airflow-core/src/airflow/ui/src/pages/TaskInstances/TaskInstances.tsx",
    "airflow-core/src/airflow/ui/src/pages/Variables/Variables.tsx",
    "providers/edge3/src/airflow/providers/edge3/plugins/www/src/components/SearchBar.tsx",
    "providers/edge3/src/airflow/providers/edge3/plugins/www/src/components/StateBadge.tsx",
    "providers/edge3/src/airflow/providers/edge3/plugins/www/src/components/WorkerStateBadge.tsx",
    "providers/edge3/src/airflow/providers/edge3/plugins/www/src/components/ui/CloseButton.tsx",
    "providers/edge3/src/airflow/providers/edge3/plugins/www/src/components/ui/toaster.tsx",
    "providers/edge3/src/airflow/providers/edge3/plugins/www/src/layouts/EdgeLayout.tsx"
  ],
  "graph_matching_files": [
    "airflow-core/src/airflow/ui/src/pages/DagsList/DagTags.tsx"
  ],
  "gold_is_only_valid_answer_in_current_graph": true,
  "flag_for_user_review": true
}
```

### code_retrieval-013

Which source file in repository apache/airflow contains the code fragment ""delta": encode_interval(timetable.delta),"?

```json
{
  "fragment": "\"delta\": encode_interval(timetable.delta),",
  "gold": [
    "airflow-core/src/airflow/serialization/encoders.py"
  ],
  "returned_entities": [
    "airflow-core/docs/administration-and-deployment/pools.rst",
    "airflow-core/docs/administration-and-deployment/scheduler.rst",
    "airflow-core/docs/administration-and-deployment/task-and-asset-state-store-cleanup.rst",
    "airflow-core/docs/authoring-and-scheduling/cron.rst",
    "airflow-core/docs/authoring-and-scheduling/deferring.rst",
    "airflow-core/docs/authoring-and-scheduling/language-sdks/index.rst",
    "airflow-core/docs/authoring-and-scheduling/timetable.rst",
    "airflow-core/docs/authoring-and-scheduling/timezone.rst",
    "airflow-core/docs/core-concepts/dag-run.rst",
    "airflow-core/docs/core-concepts/sensors.rst",
    "airflow-core/docs/core-concepts/task-state-store.rst",
    "airflow-core/docs/core-concepts/tasks.rst",
    "airflow-core/docs/faq.rst",
    "airflow-core/docs/howto/deadline-alerts.rst",
    "airflow-core/docs/howto/sla-to-deadlines.rst",
    "airflow-core/docs/howto/timetable.rst",
    "airflow-core/docs/templates-ref.rst",
    "airflow-core/docs/tutorial/pipeline.rst",
    "airflow-core/newsfragments/69143.bugfix.rst",
    "airflow-core/src/airflow/api_fastapi/common/types.py",
    "airflow-core/src/airflow/api_fastapi/core_api/datamodels/dags.py",
    "airflow-core/src/airflow/api_fastapi/core_api/routes/public/task_state_store.py",
    "airflow-core/src/airflow/api_fastapi/execution_api/datamodels/taskinstance.py",
    "airflow-core/src/airflow/api_fastapi/execution_api/versions/v2026_04_06.py",
    "airflow-core/src/airflow/dag_processing/bundles/base.py",
    "airflow-core/src/airflow/dag_processing/dagbag.py",
    "airflow-core/src/airflow/dag_processing/manager.py",
    "airflow-core/src/airflow/example_dags/example_custom_weight.py",
    "airflow-core/src/airflow/example_dags/example_latest_only_with_trigger.py",
    "airflow-core/src/airflow/example_dags/example_passing_params_via_test_command.py",
    "airflow-core/src/airflow/example_dags/example_retry_policy.py",
    "airflow-core/src/airflow/example_dags/example_skip_dag.py",
    "airflow-core/src/airflow/example_dags/example_task_state_store.py",
    "airflow-core/src/airflow/example_dags/example_time_delta_sensor_async.py",
    "airflow-core/src/airflow/example_dags/plugins/business_day_window.py",
    "airflow-core/src/airflow/example_dags/plugins/workday.py",
    "airflow-core/src/airflow/example_dags/tutorial.py",
    "airflow-core/src/airflow/migrations/versions/0117_3_3_0_change_deadline_interval_to_json.py",
    "airflow-core/src/airflow/models/dag.py",
    "airflow-core/src/airflow/models/deadline.py",
    "airflow-core/src/airflow/models/deadline_alert.py",
    "airflow-core/src/airflow/models/serialized_dag.py",
    "airflow-core/src/airflow/models/taskinstance.py",
    "airflow-core/src/airflow/models/trigger.py",
    "airflow-core/src/airflow/partition_mappers/temporal.py",
    "airflow-core/src/airflow/partition_mappers/window.py",
    "airflow-core/src/airflow/sensors/__init__.py",
    "airflow-core/src/airflow/serialization/decoders.py",
    "airflow-core/src/airflow/serialization/definitions/baseoperator.py",
    "airflow-core/src/airflow/serialization/definitions/dag.py",
    "airflow-core/src/airflow/serialization/definitions/deadline.py",
    "airflow-core/src/airflow/serialization/definitions/mappedoperator.py",
    "airflow-core/src/airflow/serialization/encoders.py",
    "airflow-core/src/airflow/serialization/enums.py",
    "airflow-core/src/airflow/serialization/schema.json",
    "airflow-core/src/airflow/serialization/serialized_objects.py",
    "airflow-core/src/airflow/timetables/_cron.py",
    "airflow-core/src/airflow/timetables/_delta.py",
    "airflow-core/src/airflow/timetables/interval.py",
    "airflow-core/src/airflow/timetables/simple.py",
    "airflow-core/src/airflow/timetables/trigger.py",
    "airflow-core/src/airflow/triggers/base.py",
    "airflow-core/tests/unit/api_fastapi/auth/test_tokens.py",
    "airflow-core/tests/unit/api_fastapi/conftest.py",
    "airflow-core/tests/unit/api_fastapi/core_api/datamodels/test_dags.py",
    "airflow-core/tests/unit/api_fastapi/core_api/routes/public/test_assets.py",
    "airflow-core/tests/unit/api_fastapi/core_api/routes/public/test_backfills.py",
    "airflow-core/tests/unit/api_fastapi/core_api/routes/public/test_dag_stats.py",
    "airflow-core/tests/unit/api_fastapi/core_api/routes/public/test_dags.py",
    "airflow-core/tests/unit/api_fastapi/core_api/routes/public/test_hitl.py",
    "airflow-core/tests/unit/api_fastapi/core_api/routes/public/test_monitor.py",
    "airflow-core/tests/unit/api_fastapi/core_api/routes/ui/test_dashboard.py",
    "airflow-core/tests/unit/api_fastapi/core_api/routes/ui/test_grid.py",
    "airflow-core/tests/unit/cli/commands/test_dag_command.py",
    "airflow-core/tests/unit/cluster_policies/__init__.py",
    "airflow-core/tests/unit/core/test_core.py",
    "airflow-core/tests/unit/core/test_example_dags_system.py",
    "airflow-core/tests/unit/dag_processing/bundles/test_base.py",
    "airflow-core/tests/unit/dag_processing/test_collection.py",
    "airflow-core/tests/unit/dag_processing/test_dagbag.py",
    "airflow-core/tests/unit/dags/test_cli_triggered_dags.py",
    "airflow-core/tests/unit/dags/test_dag_for_db_queries_counter.py",
    "airflow-core/tests/unit/dags/test_dag_version_inflation_check.py",
    "airflow-core/tests/unit/dags/test_dag_xcom_openlineage.py",
    "airflow-core/tests/unit/dags/test_example_bash_operator.py",
    "airflow-core/tests/unit/dags/test_failing.py",
    "airflow-core/tests/unit/dags/test_future_start_date.py",
    "airflow-core/tests/unit/dags/test_miscellaneous.py",
    "airflow-core/tests/unit/dags/test_missing_owner.py",
    "airflow-core/tests/unit/dags/test_multiple_dags.py",
    "airflow-core/tests/unit/dags/test_scheduler_dags.py",
    "airflow-core/tests/unit/dags/test_sensor.py",
    "airflow-core/tests/unit/dags/test_with_non_default_owner.py",
    "airflow-core/tests/unit/dags_corrupted/test_impersonation_custom.py",
    "airflow-core/tests/unit/dags_corrupted/test_nonstring_owner.py",
    "airflow-core/tests/unit/dags_with_system_exit/a_system_exit.py",
    "airflow-core/tests/unit/dags_with_system_exit/b_test_scheduler_dags.py",
    "airflow-core/tests/unit/dags_with_system_exit/c_system_exit.py",
    "airflow-core/tests/unit/executors/test_base_executor.py",
    "airflow-core/tests/unit/jobs/test_base_job.py"
  ],
  "graph_matching_files": [
    "airflow-core/src/airflow/serialization/encoders.py"
  ],
  "gold_is_only_valid_answer_in_current_graph": true,
  "flag_for_user_review": true
}
```

### code_retrieval-018

Which source file in repository apache/airflow contains the code fragment "const count = parseInt(text?.split(" ")[0] ?? "0", 10);"?

```json
{
  "fragment": "const count = parseInt(text?.split(\" \")[0] ?? \"0\", 10);",
  "gold": [
    "airflow-core/src/airflow/ui/tests/e2e/pages/AssetDetailPage.ts"
  ],
  "returned_entities": [
    "airflow-core/src/airflow/api_fastapi/auth/managers/simple/ui/openapi-gen/requests/core/serverSentEvents.gen.ts",
    "airflow-core/src/airflow/ui/src/hooks/useSelectedVersion.ts",
    "airflow-core/src/airflow/ui/src/layouts/Details/DagBreadcrumb.tsx",
    "airflow-core/src/airflow/ui/src/pages/Asset/AssetEvents.tsx",
    "airflow-core/src/airflow/ui/src/pages/Asset/AssetStateStore/AssetStateStore.tsx",
    "airflow-core/src/airflow/ui/src/pages/Dag/Overview/Overview.tsx",
    "airflow-core/src/airflow/ui/src/pages/Events/Events.tsx",
    "airflow-core/src/airflow/ui/src/pages/TaskInstance/AssetEvents.tsx",
    "airflow-core/src/airflow/ui/src/pages/TaskInstance/Details.tsx",
    "airflow-core/src/airflow/ui/src/pages/TaskInstance/ExtraLinks.tsx",
    "airflow-core/src/airflow/ui/src/pages/TaskInstance/HITLResponse.tsx",
    "airflow-core/src/airflow/ui/src/pages/TaskInstance/Logs/Logs.tsx",
    "airflow-core/src/airflow/ui/src/pages/TaskInstance/TaskInstance.tsx",
    "airflow-core/src/airflow/ui/src/pages/TaskStateStore/TaskStateStore.tsx",
    "airflow-core/src/airflow/ui/tests/e2e/pages/AssetDetailPage.ts",
    "airflow-core/src/airflow/ui/tests/e2e/pages/BackfillPage.ts",
    "airflow-core/src/airflow/ui/tests/e2e/pages/HomePage.ts",
    "providers/edge3/src/airflow/providers/edge3/plugins/www/src/components/WorkerConcurrencyButton.tsx",
    "registry/src/_data/statsData.js"
  ],
  "graph_matching_files": [
    "airflow-core/src/airflow/ui/tests/e2e/pages/AssetDetailPage.ts"
  ],
  "gold_is_only_valid_answer_in_current_graph": true,
  "flag_for_user_review": true
}
```

### code_retrieval-033

Which source file in repository apache/airflow contains the code fragment "assert result.conn_id == "target_conn""?

```json
{
  "fragment": "assert result.conn_id == \"target_conn\"",
  "gold": [
    "airflow-core/tests/unit/always/test_secrets_metastore.py"
  ],
  "returned_entities": [
    "airflow-core/tests/unit/always/test_secrets_metastore.py",
    "airflow-core/tests/unit/models/test_connection.py",
    "providers/common/sql/tests/unit/common/sql/datafusion/test_engine.py",
    "task-sdk/tests/task_sdk/execution_time/test_context_cache.py"
  ],
  "graph_matching_files": [
    "airflow-core/tests/unit/always/test_secrets_metastore.py"
  ],
  "gold_is_only_valid_answer_in_current_graph": true,
  "flag_for_user_review": true
}
```

## Validation, recovery and changed files

The full suite passed 60 tests. The seven focused Phase 1C tests then passed after adding the Windows checkpoint-lock regression test (61 distinct tests in total). Tests cover no template lookup/shortcut in any route, hybrid synthesis, shared prompt/settings, post-hoc subjects and strict N/A handling. Logs: `results/v2/phase1c/tests.txt` and `checkpoint_tests.txt`.

The first template-result import encountered a transient Windows file-replacement denial before any new model calls. Its partial journal/config are preserved in `with_templates_import_attempt1/`. A bounded local rename retry was added and the import restarted. No provider request was retried because of that local failure.

| Data integrity check | Result |
| --- | --- |
| protected_splits_unchanged | PASS |
| v1_byte_hash_unchanged | PASS |
| retained_rows_unchanged | PASS |
| only_flagged_question_removed | PASS |
| final_split_hash_matches | PASS |

| Mode | All available output-integrity checks passed |
| --- | --- |
| with_templates | True |
| no_templates | True |

Detailed checks and counts are in [validation.json](../results/v2/phase1c/validation.json). Checkpoints, attempts, response cache, raw answers, generation provenance, snapshots, complete per-question strict/recall outcomes and oracle tables are under `results/v2/phase1c/`.

Changed source, documentation and explicitly authorized split files:

- `scripts/audit_phase1b.py`
- `scripts/prepare_phase1c_tuning.py`
- `scripts/derive_oracle_routes.py`
- `scripts/inspect_phase1c.py`
- `src/systems/adaptive_hybrid_graphrag_v2.py`
- `tests/test_phase1c.py`
- `tests/test_phase1b.py`
- `docs/phase1c_protocol.md`
- `data/benchmark/splits_v2/README.md`
- `data/benchmark/splits_v2/manifest.json`
- `data/benchmark/splits_v2/router-tuning.csv`
- `data/benchmark/splits_v2/router-tuning_v1.csv`
- `reports/phase1c.md`

The complete generated-file inventory is `results/v2/phase1c/artifact_inventory.json`. Complete file contents are retained directly in the workspace. The redundant ZIP archive and stale temporary import checkpoint were removed at the user's request. Prior Phase 1B results and all protected splits remain unchanged.

Stopped at Phase 1C. Awaiting confirmation; Phase 2 was not started.

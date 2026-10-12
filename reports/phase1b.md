# Phase 1B — diagnostic route outcomes

Date: 2026-10-12 (Asia/Colombo).

**Execution status: COMPLETE_DIAGNOSTIC. 70/70 questions have all three route outcomes; 0 active route errors. Primary-entity disjointness: FAIL.**

The user explicitly authorized overlap-contaminated diagnostics and transmission of router-tuning questions and retrieved repository evidence to the configured Gemini API. No Phase 2 training, selection or freezing was performed. Hidden-test and human-test were not evaluated or modified; their metadata was read only for the requested exclusion check. No gold was edited. The old report is preserved byte-for-byte as [phase1b_blocked_2026-10-08.md](phase1b_blocked_2026-10-08.md).

## Step status

| Step | Status |
| --- | --- |
| Environment | PASS outside network sandbox |
| 0 / Part A | Verified existing metric code/tests; completed docs and missing 25-flip diagnostic fields |
| 0 / Part B | Existing split preserved; README/manifest updated; primary-entity disjointness FAIL disclosed |
| 1 / Part C | COMPLETE_DIAGNOSTIC |
| 2 / Report | Written with complete-file archive |

## Environment and frozen run settings

Neo4j verification returned these label counts (label counts are not necessarily distinct-node totals):

| Label | Count |
| --- | --- |
| Repository | 6 |
| File | 27624 |
| Commit | 5696 |
| Developer | 1807 |
| Issue | 1141 |
| PullRequest | 1506 |

The vector manifest hashes match and `diagnostic_only=false`. Ollama contains `qwen2.5:7b`; the route experiment uses Gemini. The initial sandbox connectivity failure and successful network verification are both retained.

| Setting | Value |
| --- | --- |
| Generator | gemini-flash-lite-latest |
| Answer temperature | 0.0 |
| Answer token limit | 1024 |
| Cypher token limit | 700 |
| Gemini RPM | 10 |
| Application retry budget | 6 |
| Vector k | 10 |
| Chunk size / overlap | 1200 / 180 characters |
| Route cost order | graph < vector < hybrid |
| Graph templates | Enabled, production behavior |
| Cross-route safety fallback | Disabled; graph's own Cypher-generation fallback retained |
| Cache | Shared across routes; key = model + generation parameters + prompt SHA-256 |
| Snapshot | results/v2/phase1b/route_outcomes/config_snapshot.json |

The snapshot includes the entire experiment config, source hashes, split and index hashes, model alias, retry settings and protocol. The model alias is not an immutable provider revision.

## Step 0 / Part A — existing diagnostic extended

The existing adaptive diagnostic has 25 legacy-to-strict flips (the larger saved changed-verdict file contains 114 rows across systems/ablations). This extension uses its saved predicted entities and original generation-query provenance; it does not rerun a held-out evaluation.

| Interpretation | Remaining flips |
| --- | --- |
| Strict against unchanged frozen gold | 25 |
| Strict, known-complete gold subset | 5 |
| Recall accuracy | 0 |
| Unknown completeness, excluded from strict-complete subset | 20 |

Unknown completeness is N/A for strict-complete accuracy, never a pass. Extra entities are not verified as true. Returned length counts extracted entities, not answer lines or tokens. The complete extra-entity lists are in [diagnostic_25_flips.csv](../results/v2/phase1b/diagnostic_25_flips.csv).

| Question | Gold length | Returned length | gold_complete | Extra entities (count) | Recall | Strict |
| --- | --- | --- | --- | --- | --- | --- |
| developer_activity-004 | 20 | 100 | null | 80 | 1 | 0 |
| structure-002 | 20 | 26 | null | 6 | 1 | 0 |
| code_retrieval-003 | 1 | 21 | True | 20 | 1 | 0 |
| code_retrieval-005 | 1 | 74 | True | 73 | 1 | 0 |
| structure-021 | 20 | 53 | null | 33 | 1 | 0 |
| structure-011 | 20 | 89 | null | 69 | 1 | 0 |
| structure-034 | 20 | 57 | null | 37 | 1 | 0 |
| structure-013 | 20 | 53 | null | 33 | 1 | 0 |
| code_retrieval-018 | 1 | 19 | True | 18 | 1 | 0 |
| structure-019 | 20 | 65 | null | 45 | 1 | 0 |
| structure-017 | 20 | 47 | null | 27 | 1 | 0 |
| structure-027 | 20 | 23 | null | 3 | 1 | 0 |
| structure-012 | 20 | 100 | null | 80 | 1 | 0 |
| structure-004 | 20 | 29 | null | 9 | 1 | 0 |
| code_retrieval-033 | 1 | 4 | True | 3 | 1 | 0 |
| structure-005 | 20 | 31 | null | 11 | 1 | 0 |
| structure-003 | 20 | 47 | null | 27 | 1 | 0 |
| structure-008 | 20 | 26 | null | 6 | 1 | 0 |
| structure-023 | 20 | 43 | null | 23 | 1 | 0 |
| structure-007 | 20 | 100 | null | 80 | 1 | 0 |
| code_retrieval-013 | 1 | 100 | True | 99 | 1 | 0 |
| developer_activity-027 | 20 | 36 | null | 16 | 1 | 0 |
| developer_activity-008 | 20 | 35 | null | 15 | 1 | 0 |
| multi_hop-048 | 20 | 49 | null | 29 | 1 | 0 |
| multi_hop-014 | 20 | 27 | null | 7 | 1 | 0 |

Questions with null `gold_complete` are listed below and in [gold_complete_null.csv](../results/v2/phase1b/gold_complete_null.csv). These lists cover the requested 25-flip diagnostic and router-tuning, not a new assessment of held-out splits.

**historical_25_flips: 20 questions.**

| Question | Reason |
| --- | --- |
| developer_activity-004 | generation_limit_reached_completeness_unknown |
| structure-002 | generation_limit_reached_completeness_unknown |
| structure-021 | generation_limit_reached_completeness_unknown |
| structure-011 | generation_limit_reached_completeness_unknown |
| structure-034 | generation_limit_reached_completeness_unknown |
| structure-013 | generation_limit_reached_completeness_unknown |
| structure-019 | generation_limit_reached_completeness_unknown |
| structure-017 | generation_limit_reached_completeness_unknown |
| structure-027 | generation_limit_reached_completeness_unknown |
| structure-012 | generation_limit_reached_completeness_unknown |
| structure-004 | generation_limit_reached_completeness_unknown |
| structure-005 | generation_limit_reached_completeness_unknown |
| structure-003 | generation_limit_reached_completeness_unknown |
| structure-008 | generation_limit_reached_completeness_unknown |
| structure-023 | generation_limit_reached_completeness_unknown |
| structure-007 | generation_limit_reached_completeness_unknown |
| developer_activity-027 | generation_limit_reached_completeness_unknown |
| developer_activity-008 | generation_limit_reached_completeness_unknown |
| multi_hop-048 | generation_limit_reached_completeness_unknown |
| multi_hop-014 | generation_limit_reached_completeness_unknown |

**router-tuning: 12 questions.**

| Question | Reason |
| --- | --- |
| router-tuning-e768f2d99051b998 | generation_limit_reached_completeness_unknown |
| router-tuning-84250bc7c92f8c92 | generation_limit_reached_completeness_unknown |
| router-tuning-bcad8e41c23b7df6 | generation_limit_reached_completeness_unknown |
| router-tuning-ddbea72d99d60e78 | generation_limit_reached_completeness_unknown |
| router-tuning-528c152157c34d4f | generation_limit_reached_completeness_unknown |
| router-tuning-cf875b04368290f8 | generation_limit_reached_completeness_unknown |
| router-tuning-5534e3e19715a447 | generation_limit_reached_completeness_unknown |
| router-tuning-a775fd640a6d104d | generation_limit_reached_completeness_unknown |
| router-tuning-4c9cc9e4842836b3 | generation_limit_reached_completeness_unknown |
| router-tuning-6728fa2b7f6ba88e | generation_limit_reached_completeness_unknown |
| router-tuning-c0a825004bf11e7b | generation_limit_reached_completeness_unknown |
| router-tuning-5c43a188451842b5 | generation_limit_reached_completeness_unknown |

## Step 0 / Part B — frozen split and exclusion audit

The existing 70 questions were retained; none were regenerated. New generation seed: `20261009` (original benchmark: `42`). Tuning-only SHA-256: `fee8bab59925109abfff7d7b579fa1df92800962403200116fd329f2ce539aa8`.

| Category | Questions |
| --- | --- |
| code_retrieval | 10 |
| dependency_analysis | 10 |
| developer_activity | 10 |
| documentation_lookup | 10 |
| issue_pr_analysis | 10 |
| multi_hop | 10 |
| structure | 10 |

| Repository | Questions |
| --- | --- |
| dotnet/eShop | 13 |
| mlflow/mlflow | 14 |
| openmrs/openmrs-core | 20 |
| spring-projects/spring-petclinic | 16 |
| synthetic-org/platform | 7 |

No category is missing. `apache/airflow` is absent by the existing generation policy.

| Compared split | Normalized text overlaps | Primary-subject overlap pairs | Result |
| --- | --- | --- | --- |
| development | 0 | 4 | FAIL |
| validation | 0 | 1 | FAIL |
| hidden-test | 0 | 2 | FAIL |
| human-test | 0 | 0 | PASS_DETECTABLE_SUBJECTS |

The audit exits 1 on detected overlap. It checks repository-scoped query subjects rather than whole expected-answer sets. Code/doc fragments use file identities; a generic keyword is not an entity. For repository-wide questions, the repository itself is the primary subject. Human questions have no subject annotations, so zero literal matches cannot prove semantic disjointness.

| Tuning question | Other split / question | Subject type | Subject |
| --- | --- | --- | --- |
| router-tuning-c6dc0e1b1b05a2df | development / developer_activity-006 | developer | choonghee.lee@hotmail.com |
| router-tuning-cf875b04368290f8 | development / issue_pr_analysis-015 | repository | dotnet/eshop |
| router-tuning-cf875b04368290f8 | development / issue_pr_analysis-033 | repository | dotnet/eshop |
| router-tuning-cf875b04368290f8 | development / issue_pr_analysis-014 | repository | dotnet/eshop |
| router-tuning-d26ff3ef6ba314c1 | validation / issue_pr_analysis-049 | repository | openmrs/openmrs-core |
| router-tuning-cf875b04368290f8 | hidden-test / developer_activity-013 | repository | dotnet/eshop |
| router-tuning-d26ff3ef6ba314c1 | hidden-test / developer_activity-001 | repository | openmrs/openmrs-core |

The original generator excluded equal complete answer sets, which did not prevent these overlaps. The README and manifest now disclose tuning-only diagnostic use and failed primary-entity disjointness. User authorization permits the diagnostic run; it does not make the split disjoint.

## Step 1 / Part C — route outcomes

The runner forces each route through the existing production retrieval and answering implementation (`adaptive_hybrid_graphrag_v2.System`, inherited graph retrieval, shared vector search/fusion and grounded answering). It does not train or select RouterV2. Templates are enabled for graph access; these measurements therefore do not isolate routing from template-answer access.

Each route outcome is appended before proceeding, and CSV/progress files are checkpointed after every route, hence every question. All API attempts and question-route starts/completions are logged under the run directory. Errors count as incorrect. Quota errors retain their failed attempt, stop the run after the existing retry budget, and are retried on a later invocation; other completed errors remain in the denominator. Earlier attempts are retained.

The oracle chooses the first recall-correct route in `graph < vector < hybrid`; measured latency does not choose the label. `oracle_best_accuracy` and `oracle_best_strict_accuracy` are separate per-question maxima. An oracle requires all three routes for that question. `no_route_correct` means none was recall-correct. Pacing and backoff are subtracted from per-route latency. Cached and failed/retried rows are excluded from the clean latency mean; counts disclose the denominator.

| Route | Attempted questions | Recall accuracy | Strict accuracy | Errors | Clean latency (s) | Clean n |
| --- | --- | --- | --- | --- | --- | --- |
| graph | 70 | 94.29% | 81.43% | 0 | 0.126 | 70 |
| vector | 70 | 10.00% | 10.00% | 0 | 1.349 | 70 |
| hybrid | 70 | 94.29% | 81.43% | 0 | 0.208 | 70 |

| Category | Complete questions | Graph cheapest | Vector cheapest | Hybrid cheapest | No route correct |
| --- | --- | --- | --- | --- | --- |
| ALL | 70 | 66 | 0 | 0 | 4 |
| code_retrieval | 10 | 10 | 0 | 0 | 0 |
| dependency_analysis | 10 | 9 | 0 | 0 | 1 |
| developer_activity | 10 | 8 | 0 | 0 | 2 |
| documentation_lookup | 10 | 10 | 0 | 0 | 0 |
| issue_pr_analysis | 10 | 10 | 0 | 0 | 0 |
| multi_hop | 10 | 9 | 0 | 0 | 1 |
| structure | 10 | 10 | 0 | 0 | 0 |

| Category | Route | n | Recall accuracy | Strict accuracy | Errors |
| --- | --- | --- | --- | --- | --- |
| code_retrieval | graph | 10 | 100.00% | 80.00% | 0 |
| code_retrieval | vector | 10 | 20.00% | 20.00% | 0 |
| code_retrieval | hybrid | 10 | 100.00% | 80.00% | 0 |
| dependency_analysis | graph | 10 | 90.00% | 90.00% | 0 |
| dependency_analysis | vector | 10 | 0.00% | 0.00% | 0 |
| dependency_analysis | hybrid | 10 | 90.00% | 90.00% | 0 |
| developer_activity | graph | 10 | 80.00% | 50.00% | 0 |
| developer_activity | vector | 10 | 0.00% | 0.00% | 0 |
| developer_activity | hybrid | 10 | 80.00% | 50.00% | 0 |
| documentation_lookup | graph | 10 | 100.00% | 90.00% | 0 |
| documentation_lookup | vector | 10 | 20.00% | 20.00% | 0 |
| documentation_lookup | hybrid | 10 | 100.00% | 90.00% | 0 |
| issue_pr_analysis | graph | 10 | 100.00% | 100.00% | 0 |
| issue_pr_analysis | vector | 10 | 20.00% | 20.00% | 0 |
| issue_pr_analysis | hybrid | 10 | 100.00% | 100.00% | 0 |
| multi_hop | graph | 10 | 90.00% | 90.00% | 0 |
| multi_hop | vector | 10 | 10.00% | 10.00% | 0 |
| multi_hop | hybrid | 10 | 90.00% | 90.00% | 0 |
| structure | graph | 10 | 100.00% | 70.00% | 0 |
| structure | vector | 10 | 0.00% | 0.00% | 0 |
| structure | hybrid | 10 | 100.00% | 70.00% | 0 |

Vector is the cheapest correct route on **0/70 (0.00%)** complete questions. Vector is almost never best under this ordinal cost rule. No route is correct on **4/70** complete questions. Graph wins every graph-correct tie by construction; graph template access and the generated question distribution limit any general conclusion about vector retrieval.

Graph and hybrid returned identical answers for **70/70** completed pairs; **70/70** pairs used deterministic graph answering in both routes. Hybrid still executed vector retrieval, but the production shortcut chooses graph answers when available. This explains the answer/accuracy tie and is not evidence that hybrid fusion or an LLM independently reached the same answer.

## Validation and changed files

The full local suite passed 53 tests. After adding the provider-quota telemetry test, all five Phase 1B tests passed (54 distinct tests in total). Logs: `results/v2/phase1b/tests.txt` and `phase1b_tests.txt`. These test ordinal cost selection, independent oracle maxima, error handling, partial checkpoints, replacement of quota attempts, entity overlap and quota telemetry.

| Saved-output integrity check | Result |
| --- | --- |
| split_hashes_unchanged | PASS |
| source_hashes_match_run | PASS |
| only_router_tuning_outcomes | PASS |
| no_route_escalation | PASS |
| errors_incorrect | PASS |
| latency_excludes_waits | PASS |
| oracle_dominates_both_metrics | PASS |
| completed_question_count_matches | PASS |
| run_is_complete_or_quota_stopped | PASS |
| all_70_if_complete | PASS |
| attempt_starts_and_completions_logged | PASS |
| api_attempts_logged | PASS |
| api_event_file_matches_records | PASS |
| saved_oracle_matches_derivation | PASS |

Logged API attempts: 70; cache hits: 0. These integrity checks do not override the failed split-disjointness check.

Source/documentation files changed in this continuation:

- `scripts/audit_phase1b.py`
- `scripts/derive_oracle_routes.py`
- `src/llm.py`
- `tests/test_phase1b.py`
- `tests/test_router_v2.py`
- `docs/metrics.md`
- `data/benchmark/splits_v2/README.md`
- `data/benchmark/splits_v2/manifest.json`
- `reports/phase1b.md`
- `reports/phase1b_blocked_2026-10-08.md`

Generated artifacts live under `results/v2/phase1b/`: environment checks, audit/snapshot, diagnostic tables, null-completeness list, test logs, report renderer, validation, and `route_outcomes/` (configuration snapshot, response cache, attempt/API logs, outcomes, progress, oracle tables and per-category summaries). The complete generated-file inventory and hashes are in `artifact_inventory.json`.

Complete source, documentation, report and result file contents (not diffs) are supplied in [phase1b_complete_files.zip](../results/v2/phase1b/phase1b_complete_files.zip). Gold, all split CSV bytes, the index and historical result files were preserved.

Stopped at Phase 1B. Awaiting confirmation; do not start Phase 2.

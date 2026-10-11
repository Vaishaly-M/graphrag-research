# Phase 1 — evaluation freeze and measurement harness

Date: 2026-10-08 (Asia/Colombo). Completion checkout HEAD: `ed647d697a8965671acae2b92d5fb84c55898253`. This completes the Phase 1 implementation and records empirical limitations below; no later phase is authorized or started. Gold and historical results were not edited. Router, baseline prompts, routing policy, fusion and answering behavior were not tuned. The existing apostrophe parser was retained and tested; the only retrieval change is adaptive over-fetching for repository/kind filters.

## 1. Latency microbenchmark

Ten fixed questions per system; Plain has trivial-prompt and full-system calls, Vector additionally has retrieval-only calls. All attempts, including prior failures, remain in [latency_probe.csv](../results/v2/latency_probe.csv). Superseded failed attempts are excluded from the following means. Values are seconds per operation. Initialization/index building is outside question timing; first index load is inside retrieval timing.

| System | Operation | N | Errors | Attempt time | Pacing | Backoff | Retrieval | Wall | Attempts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| plain_llm | full_system | 10 | 0 | 1.637 | 5.992 | 0.000 | 0.000 | 7.633 | 10 |
| plain_llm | trivial_llm | 10 | 0 | 1.849 | 5.396 | 0.000 | 0.000 | 7.249 | 10 |
| vector_rag | full_system | 10 | 0 | 1.842 | 4.633 | 0.127 | 0.405 | 7.014 | 11 |
| vector_rag | retrieval_only | 10 | 0 | 0.000 | 0.000 | 0.000 | 0.400 | 0.419 | 0 |
| vector_rag | trivial_llm | 10 | 0 | 1.551 | 5.383 | 0.000 | 0.000 | 6.946 | 10 |

Total recorded client attempts across retained history (including earlier connection failures): 61; cap: 61, enforced persistently before each SDK request. The default cap was 60; one extra attempt completed the final question after a transient retry. Active rows around 175 seconds (170–180): 0; active rows using all six attempts: 0. Model/prompt/parameter response caching prevents repeat API requests on resume; cache hits are labeled and excluded from latency summaries. See per-call start/end timestamps and attempt_events for duration, error type, pacing, backoff and retry-after. Events are also appended to logs/llm_events.jsonl.

**Historical ~175-second cause remains unidentifiable from saved evidence.** It was not reproduced by successful current model calls. The old CSVs contain wall-like latency only, with no attempt or sleep fields:

| Historical system | 170–180 s rows | Attempt time | Pacing | Backoff | Six attempts? |
| --- | --- | --- | --- | --- | --- |
| plain_llm | 125 | unrecorded | unrecorded | unrecorded | unrecorded |
| vector_rag | 235 | unrecorded | unrecorded | unrecorded | unrecorded |

At RPM=10, one pacing wait is at most approximately six seconds. Six application attempts have five exponential backoffs totaling 31 seconds before jitter/provider retry-after; this alone does not explain 175 seconds. Network/SDK attempt time and provider retry-after are possible contributors, not established causes. The claim that historical 175-second rows exhausted six attempts cannot be verified. The repaired client disables hidden SDK retries and sets a recorded 60-second request timeout so future calls are auditable. Historical model/configuration provenance is incomplete; current configured aliases are recorded in each invocation snapshot. A mocked six-attempt test verifies timing accounting, not the historical cause.

Vector latency uses a byte-identical diagnostic copy of the preserved legacy index (131,179 chunks). 14,336 explicitly recomputed embeddings match the corresponding legacy vectors within 2e-6; the full document serialization matches the rebuild corpus hash. This is a compatibility check on a prefix subset, not proof of historical model/chunk/source settings. Unknown historical manifest fields remain null. The diagnostic manifest is marked diagnostic_only and normal run_eval runs reject it. VectorStore.build writes a complete manifest at actual build time and refuses loading any index without a manifest. The fresh rebuild was checkpointed and stopped before the full corpus completed; an explicit complete build is still required before new publishable vector evaluations. No background build or model request remains running at handoff.

One Vector call encountered ServerError, spent approximately 0.302 seconds in the failed attempt and 1.267 seconds in backoff, then succeeded on attempt two. No provider retry-after was reported.

## 2. Diagnostic rescore (not paper results)

All saved final-evaluation and ablation answers were read without rerunning systems. Strict accuracy uses boundary-aware category/answer-type entities and closed-set extra-entity penalties. Errors score zero; conditional non-error accuracy is separate. Missing human gold is N/A. Definitions, precision/recall/F1 relationships and limitations are in [docs/metrics.md](../docs/metrics.md).

| System/variant | Rows | Legacy accuracy | Strict accuracy | Errors | Abstentions |
| --- | --- | --- | --- | --- | --- |
| adaptive_hybrid_graphrag | 242 | 96.69% | 86.36% | 0 | 0 |
| fixed_graph_rag | 242 | 96.28% | 85.95% | 1 | 0 |
| fixed_hybrid_rag | 242 | 96.69% | 86.36% | 0 | 0 |
| langchain_graphrag | 242 | 64.05% | 64.88% | 0 | 39 |
| llamaindex_graphrag | 242 | 63.64% | 64.46% | 0 | 38 |
| oracle_hybrid_rag | 242 | 96.28% | 85.95% | 0 | 1 |
| plain_llm | 242 | 0.00% | 0.00% | 0 | 237 |
| vector_rag | 242 | 6.20% | 6.20% | 0 | 209 |
| ablation/fixed_1hop | 29 | 100.00% | 100.00% | 0 | 0 |
| ablation/fixed_2hop | 29 | 100.00% | 100.00% | 0 | 0 |
| ablation/fixed_3hop | 29 | 100.00% | 100.00% | 0 | 0 |
| ablation/full_system | 29 | 100.00% | 100.00% | 0 | 0 |
| ablation/fusion_equal_weight | 29 | 100.00% | 100.00% | 0 | 0 |
| ablation/fusion_graph_heavy | 29 | 100.00% | 100.00% | 0 | 0 |
| ablation/fusion_vector_heavy | 29 | 100.00% | 100.00% | 0 | 0 |
| ablation/no_fallback | 29 | 100.00% | 100.00% | 0 | 0 |
| ablation/no_graph | 29 | 10.34% | 10.34% | 0 | 25 |
| ablation/no_routing | 29 | 100.00% | 100.00% | 0 | 0 |
| ablation/no_templates | 29 | 86.21% | 86.21% | 0 | 0 |
| ablation/no_validation | 29 | 100.00% | 100.00% | 0 | 0 |
| ablation/no_vector | 29 | 100.00% | 100.00% | 0 | 0 |

114 system/question verdicts changed. Complete IDs are listed below; entity-level reasons are in [changed_verdicts.csv](../results/v2/changed_verdicts.csv). Extra output entities can reflect LIMIT-truncated gold, so these diagnostic changes must not be interpreted as adjudicated hallucinations. Gold was not expanded.

| System | Legacy to strict | Question IDs |
| --- | --- | --- |
| ablation/no_templates | 0.0 to 1 | issue_pr_analysis-021 |
| ablation/no_templates | 1.0 to 0 | developer_activity-029 |
| adaptive_hybrid_graphrag | 1.0 to 0 | developer_activity-004, structure-002, code_retrieval-003, code_retrieval-005, structure-021, structure-011, structure-034, structure-013, code_retrieval-018, structure-019, structure-017, structure-027, structure-012, structure-004, code_retrieval-033, structure-005, structure-003, structure-008, structure-023, structure-007, code_retrieval-013, developer_activity-027, developer_activity-008, multi_hop-048, multi_hop-014 |
| fixed_graph_rag | 1.0 to 0 | developer_activity-004, structure-002, code_retrieval-003, code_retrieval-005, structure-021, structure-011, structure-034, structure-013, code_retrieval-018, structure-019, structure-017, structure-027, structure-012, structure-004, code_retrieval-033, structure-005, structure-003, structure-008, structure-023, structure-007, code_retrieval-013, developer_activity-027, developer_activity-008, multi_hop-048, multi_hop-014 |
| fixed_hybrid_rag | 1.0 to 0 | developer_activity-004, structure-002, code_retrieval-003, code_retrieval-005, structure-021, structure-011, structure-034, structure-013, code_retrieval-018, structure-019, structure-017, structure-027, structure-012, structure-004, code_retrieval-033, structure-005, structure-003, structure-008, structure-023, structure-007, code_retrieval-013, developer_activity-027, developer_activity-008, multi_hop-048, multi_hop-014 |
| langchain_graphrag | 0.0 to 1 | issue_pr_analysis-031, issue_pr_analysis-017, dependency_analysis-005, dependency_analysis-034 |
| langchain_graphrag | 1.0 to 0 | multi_hop-048, multi_hop-014 |
| llamaindex_graphrag | 0.0 to 1 | issue_pr_analysis-031, developer_activity-003, issue_pr_analysis-017, dependency_analysis-005 |
| llamaindex_graphrag | 1.0 to 0 | multi_hop-048, multi_hop-014 |
| oracle_hybrid_rag | 1.0 to 0 | developer_activity-004, structure-002, code_retrieval-003, code_retrieval-005, structure-021, structure-011, structure-034, structure-013, code_retrieval-018, structure-019, structure-017, structure-027, structure-012, structure-004, code_retrieval-033, structure-005, structure-003, structure-008, structure-023, structure-007, code_retrieval-013, developer_activity-027, developer_activity-008, multi_hop-048, multi_hop-014 |

The requested ten-file fixture has strict_accuracy=1 and required_fact_coverage=1; prose title matching, number-versus-title rejection, 475-versus-abstention, extra files/commits, boundary errors, negation and dictionary-key exclusions have tests. Historical swallowed errors cannot be inferred when the saved records contain no trace. New telemetry catches swallowed retrieval, LLM and parse failures.

## 3. Frozen split definition

| Split | Questions |
| --- | --- |
| development | 29 |
| validation | 29 |
| hidden-test | 242 |
| human-test | 100 |

The category-table denominator is the full 300-template pool; the main-table denominator is its 242-question hidden-test partition after 29 development and 29 validation exclusions. These are distinct populations, not missing evaluations. Existing memberships and stable IDs are preserved in byte-identical copies under data/benchmark/splits_v2, with hashes and a README. Development is the only tuning split; validation is a locked selection check; hidden-test is held out; human-test is never used for tuning. Development/validation contain no Airflow, structure or code_retrieval rows; this imbalance is disclosed rather than repaired after seeing results. No saved paraphrased set exists and none was generated.

## 4. Human set validation

Columns: question_id, author_persona, repo, category, question. 100 rows; zero nulls in supplied columns, duplicate IDs, duplicate full rows, or duplicate normalized questions. All repositories and category labels map to the template taxonomy.

| Repository | Rows |
| --- | --- |
| spring-projects/spring-petclinic | 20 |
| openmrs/openmrs-core | 20 |
| dotnet/eShop | 20 |
| apache/airflow | 20 |
| mlflow/mlflow | 20 |

| Category | Rows |
| --- | --- |
| Structure | 15 |
| Code retrieval | 14 |
| Dependency analysis | 14 |
| Documentation lookup | 14 |
| Issue/PR analysis | 14 |
| Developer activity | 14 |
| Multi-hop reasoning | 15 |

**Author attention: Q001–Q100 all require annotations.** Answerable/unanswerable counts are unknown; no gold answers, expected entities, required facts, answer types or gold evidence are supplied. Fill the separate [human_gold_needed.csv](../results/v2/human_gold_needed.csv) worksheet; the original CSV and frozen copy remain unchanged. Answerability plus expected entities/reference answers determine answer accuracy; answer_type selects extraction; required_facts supports fact coverage; gold_evidence supports evidence metrics. Unanswerable rows need an explicit false label and should not be given invented entities. Human repo/category display fields are mapped only in the evaluator.

Leakage review: 0 exact text matches; 0 flagged pairs involving 0 human questions. The check uses punctuation/case-normalized exact text, SequenceMatcher text similarity and identifier-set Jaccard similarity; either score =0.90 flags review. Identifier sets include paths/repository slugs, hashes, emails, numbers and quoted symbols from question text because human gold is absent. This is a lexical leakage screen, not a semantic or provenance guarantee. The closest template for each human row and all flagged pairs are saved in [leakage_review.csv](../results/v2/leakage_review.csv).

## 5. Reproducibility, checks and remaining limits

Single entry point: `python scripts/run_eval.py <system> <split> --repeats N --run-name X [--discard-first-run] [--no-cache]`. Default is one measured repeat with no warm-up exclusion. Discarding the first requires at least two requested repeats. Every run records model/temperature/seed/RPM/retry settings, k/chunking/embedding, thresholds, index and benchmark hashes, source hashes, Git revision and dirty state. Generation seed remains null because existing systems did not set one. Frozen-file hash changes fail loudly. Configuration changes require a new run name. Resume retains failed rows, their attempt_number and superseded=true; repeats have separate cache namespaces. Latency is total_wall_s minus pacing/backoff; successful retry time remains included. Cached and execution-error rows are excluded from latency means, but execution errors remain in accuracy denominators.

Environment check (the script exits nonzero if any required check fails):

| Component | Observation |
| --- | --- |
| Gemini | Key present: True; configured model: gemini-flash-lite-latest. Actual probe calls verify access separately. |
| Neo4j | {"status": "error", "error_type": "ValueError", "node_counts": null, "address_resolution_failed": true} |
| Vector index | {"status": "error", "directory": "C:\\Users\\ADMIN\\Documents\\Sem\\4-Research\\My Research\\Experiment\\graphrag-research-starter\\graphrag-research\\data\\vector_index", "error_type": "FileNotFoundError", "diagnostic_copy_available": true} |
| Ollama | {"status": "ok", "models": ["gemma4:latest", "llama3.1:latest"], "qwen2_5_pulled": false} |

Neo4j checks could not resolve the configured address even with network access; node counts are unavailable, not zero. Ollama is reachable but qwen2.5 is not pulled. No graph reload, model installation, baseline rewrite or routing experiment was performed to conceal these failures.

Validation: 35 harness/metrics/retrieval tests and two standalone registry tests passed (37 total). Test records: [harness/metrics/retrieval suite](../results/v2/tests/phase1_tests.txt) and [registry title parser suite](../results/v2/tests/title_parser_tests.txt). Tests cover the new accounting and scoring behavior; these are not claims that external infrastructure is healthy.

## 6. Changed files and complete contents

The following Phase 1 implementation files include work already present in the phase-1 commit and the completion fixes. Full files are available in the workspace and in results/v2/phase1_complete_files.zip, without diffs.

- `src/llm.py`
- `src/common.py`
- `src/systems/base.py`
- `src/vector_store.py`
- `src/systems/query_registry.py`
- `src/build_vector_index.py`
- `src/evaluation/harness_v2.py`
- `src/evaluation/telemetry.py`
- `src/evaluation/reproducibility.py`
- `src/evaluation/metrics_v2.py`
- `scripts/run_eval.py`
- `scripts/latency_probe.py`
- `scripts/freeze_evaluation.py`
- `scripts/rescore_old_answers.py`
- `scripts/verify_environment.py`
- `scripts/report_phase1.py`
- `scripts/prepare_latency_index.py`
- `tests/test_harness_v2.py`
- `tests/test_metrics_v2.py`
- `tests/test_phase1_retrieval.py`
- `scripts/test_issue_title_parser.py`
- `docs/metrics.md`

Additional artifacts: data/benchmark/splits_v2/{development,validation,hidden-test,human-test}.csv, manifest.json and README.md; logs/llm_events.jsonl; results/v2 latency/cache/snapshot/index artifacts, environment checks, rescore summaries/per-question verdicts, human validation/annotation worksheet, leakage review, test logs, and this report. The registry apostrophe fix and its standalone tests were already present when completion began; no further parser edit was needed. Existing .review_tools deletions were left untouched.

Original human CSV SHA-256: `1f7dad16b56f10924233d2c728ef776401be24bc9cf4cd8a420dd3cd023ce390` (matches the Phase 0 audit). A Git content check against the completion-start HEAD found no edits to protected historical results, original benchmark files, legacy metrics, router or baselines.

**Stopped at Phase 1. Awaiting author review and confirmation before any later phase.**

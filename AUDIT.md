# Experiment audit

Date: 2026-10-14 (Asia/Colombo). Read `CLAUDE.md`; no code, results, configuration, gold answers or splits changed. No API/database/experiment runs were performed. This audit is the only new artifact.

Scope: the historical experiment with Oracle 96.28%, Adaptive 96.69% and Vector 6.20%, identified in `results/final_evaluation_metrics/summary_metrics.csv:2-9`. Current HEAD: `e120abd944f88f270614ab5c0f8d8581d834dc25`. Historical source marked **H@45f8ac56** was inspected with read-only `git show`; that is the earlier audit revision, not a verified execution-time freeze. Unqualified citations refer to today's checkout. Later v2 results do not retroactively validate the old experiment. `CLAUDE.md:20-35` specifies the intended new fairness, splits, freeze and telemetry rules. The existing Phase 0 report supplied leads; principal findings below were independently checked against code and CSVs.

CSV citations use physical starting lines, accounting for quoted multiline records. IDs disambiguate records. No numbered manuscript was supplied; tables and figures are identified by their actual saved filenames. Unknown provenance is stated rather than guessed.

## 1. Oracle implementation, per-question routing and fallback

**Classification: oracle design flaw plus a historical parser bug. The deficit does not establish superiority over a valid oracle.**

`src/systems/oracle_hybrid_rag.py:58-76` reads `expected_retrieval_route` from its benchmark input by exact question-text match. These labels originate in category rules, not measured route outcomes: `src/benchmark_gen/generate_benchmark.py:299-305,394-417` assigns vector to code/documentation, hybrid to multi_hop, graph otherwise. Oracle defaults to hybrid for an unknown question and overrides a gold route to hybrid when the registry template says hybrid (`oracle_hybrid_rag.py:97-120`).

Saved route pairs: graph→graph 127, vector→hybrid 71, hybrid→hybrid 44. Thus Oracle actually uses **127 graph, 115 hybrid, zero vector**, identical to Adaptive's selected route on all 242 questions. Appendix A lists every question's gold label, actual Oracle/Adaptive routes and fallback flag with raw CSV lines.

Oracle chooses template OR generated Cypher and executes once (`oracle_hybrid_rag.py:78-95`); an empty template result does not trigger generated Cypher. It runs vector only for vector/hybrid routes (`:128-132`), fuses evidence (`:134-136`) and prefers graph answer fields (`:138-169`). Its unknown-label default is not an evidence-triggered fallback. Adaptive validates template results, falls through to LLM Cypher, and can rescue unsuccessful graph retrieval with vector (`src/systems/adaptive_hybrid_graphrag.py:119-166,214-233`). The saved Adaptive chain ran once; Oracle has no equivalent chain.

The only answer difference between Oracle and Adaptive is `issue_pr_analysis-030`: “What is the issue number for 'Can't find API Getway project' in repository dotnet/eShop?” Oracle saved title parameter `Can`, graph count=0, vector count=0 and “Insufficient repository evidence.” Adaptive logged an invalid empty registered-template attempt followed by valid LLM Cypher, returned `475`, and did not need vector. Fixed Hybrid retrieved ten vector rows and also returned `475`. Exact row citations are supplied in Appendix A and the examples below.

Consequently Oracle=233/242=96.28099%, Adaptive/Fixed Hybrid=234/242=96.69421%. Oracle has 241 deterministic graph answers and one no-evidence answer; Adaptive has 242 deterministic graph answers. Today's apostrophe parser is already corrected (`src/systems/query_registry.py:237-259`): current source is not the source of the saved truncated parameter.

The oracle uses less effective information than Adaptive by omitting recovery. That violates the requested oracle requirement and `CLAUDE.md:21-23`. Always choosing hybrid would not itself guarantee an upper bound: fusion ranks/truncates evidence (`src/systems/retrieval_core.py:208-253`), and generation need not improve monotonically with more evidence. A valid empirical outcome oracle must include the exact Adaptive output among cached route/fallback candidates and select the maximum under a declared metric. A label-driven router is a legitimate baseline if named accordingly. A fresh stochastic answer can legitimately worsen with more context; that does not justify this baseline's upper-bound claim.

## 2. Accuracy versus Entity F1

Legacy accuracy means **all expected entity strings occur somewhere in the answer** (`src/evaluation/metrics.py:403-451`). It does not require exact equality, penalize extra entities, verify relations or reject contradictions. The initial substring test also admits matches that boundary checking would reject. Gold entities come from expected_entities, else expected_answer; predictions come from predicted_entities, else regex extraction (`:553-597,1333-1417`). Required-fact coverage is separate, not an accuracy gate.

Entity precision is exact normalized set intersection divided by predicted-set size; recall divides by gold-set size; F1 is their harmonic mean (`:328-364`). Extraction recognizes paths, #numbers, hashes and quoted symbols, not all bare numbers, email IDs, full issue titles or composite IDs. This schema mismatch produces zero F1 for some correct answers. The old summary averages successful rows (`:1824-1885`). Appendix B prints the exact functions and wiring. Appendix C prints five saved questions, answers/gold excerpts, extracted predictions and scores with file/line evidence.

One especially revealing example is developer_activity-004: the answer contains 100 composite commit IDs against 20 gold IDs. Accuracy accepts the superset; regex extraction splits IDs into repository/hash pieces and F1 becomes zero. Other examples include bare `475` and `email:maximebeauchemin@gmail.com`, which extract no entities. These discrepancies do not prove every answer is semantically wrong; they prove the metrics measure different constructs. Later metrics_v2/rescoring must be labeled separately from the original scores.

## 3. The 242/300 split and table/figure populations

`src/benchmark_gen/split_benchmark.py:44-48,78-119,122-145,197-250`: seed 42; select a real repository from sorted eligible slugs, select the rarest template per multi-template category with seeded tie-breaking, reserve repository OR template holdouts, then shuffle remaining rows within category and allocate rounded 25% development, 25% validation, remainder test. Fractions apply to the non-holdout remainder, not all 300.

`data/benchmark/splits/split_manifest.json:1-19`: Airflow holdout=136; additional non-Airflow template holdout=48; remaining=116, split 29 development +29 validation +58 test. Test=136+48+58=242. Holdout templates: top_repository_contributors, files_modified_by_commit, lowest_numbered_open_issue, developers_modifying_file. The runner-facing file strips answer/Cypher/params fields but retains route labels/template metadata (`split_benchmark.py:50-61,148-149`).

Full-pool category counts: structure 40, code_retrieval 40, dependency_analysis 45, documentation_lookup 35, issue_pr_analysis 50, developer_activity 30, multi_hop 60 (total 300). Final hidden-test category counts: respectively **40, 40, 35, 31, 32, 20, 44** (total 242). Evidence: `data/benchmark/benchmark_300.csv:1`, `data/benchmark/splits/hidden_test_answer_key.csv:1`, counted by stable ID. Final hop counts are 1-hop=143, 2-hop=55, 3+-hop=44 (all labeled 4), zero-hop=0.

The 300-question category-composition table describes the benchmark pool. The actual saved final performance category table uses **242**, not 300. This resolves the ambiguity in `reports/phase1.md:86`: its generic “category-table” wording must not be applied to final_evaluation_metrics/report_tables/category_breakdown.csv. Table builders aggregate the supplied per-question frame without a separate split filter (`src/evaluation/report_tables.py:74-153,190-235,260-273`). Appendix D inventories every saved legacy aggregate CSV and its population, including all thirteen development ablations and subsidiary runs.

Final main/summary tables contain eight system rows over 242 questions each (1,936 answer records). Failure-analysis has six failure-type rows, not six questions. Statistical tests use the per-row `n` paired denominator, with subgroup counts as above. Regression tables use seven questions/system, one/category; development ablations use 29/variant. No saved ablation_table.csv was found, although `report_tables.py:156-187` can build one.

Figures found: `results/rouge_l.png`, `results/token_f1.png`, `results/bertscore.png`, `results/latency_s.png`, and `results/final_evaluation_metrics/hallucination_heatmap.png`. The four root plots' generator reads **results/summary_metrics.csv**, not the final summary (`src/evaluation/plots.py:3-5`). That source mixes repeats and missing references; Appendix D gives raw, unique and usable denominators. No run-bound provenance guarantees the saved images match today's CSV. They are not verified final-test plots.

No code/reference generating hallucination_heatmap.png was found. Its neighboring metrics contain 242 questions/system, but the image's true denominator is **unverified** without provenance; regenerate it rather than assume. No saved scalability figure was found. `results/scalability.csv:2-3` measures two synthetic sizes, zero benchmark questions, five timed repeats/query shape/size plus warm-up (`src/scalability/generate_and_measure.py:44-45,133-143`). README's split table (`README.md:87-96`) describes 300/29/29/242; its systems table (`:178-189`) has no question denominator. Later v2 phase reports are separate experiments, not sources for the quoted legacy scores.

## 4. Latency and 175/176 seconds

Historical H@45f8ac56 `src/systems/base.py:420-462` times self.answer plus normalization/exception handling with perf_counter. Retrieval, query embedding, network/generation, pacing and retry sleeps are included. Constructors, including SentenceTransformer initialization, precede the timer. First-search disk index loading is inside it; the index is not rebuilt per question (H `src/vector_store.py:46-59`). Neo4j connection/server cache state can affect first query. Final records use run_id=1, without discarded warm-up. Historical resume deletes prior failed rows (H `base.py:343-356`); summary latency excludes unsuccessful rows (`metrics.py:1824-1885`).

The main table uses median (`report_tables.py:100-102`); summary_metrics uses mean. Independently computed from 242 saved rows/system:

| System | Mean s | Median s | Min s | Max s |
|---|---:|---:|---:|---:|
| Plain LLM | 95.080201 | 175.316631 | 1.735930 | 177.403330 |
| Vector RAG | 177.585978 | 176.219133 | 170.092621 | 341.893248 |
| Adaptive | 1.069926 | 0.288776 | 0.142398 | 175.863103 |
| Oracle | 0.312365 | 0.293206 | 0.155008 | 2.657328 |

Evidence: `results/final_evaluation/{plain_llm,vector_rag,adaptive_hybrid_graphrag,oracle_hybrid_rag}_results.csv:1`, final summary/main-performance rows 2-9. Thus 175/176 are medians, not both means.

- H `src/llm.py:34-47,99-114`: environment/configurable RPM, default 10, paced per key since previous successful completion; up to ~6 seconds at 10 RPM, not enough alone to explain 175 seconds.
- H `src/llm.py:118-122`, `src/common.py:212-268`: six application attempts for transient connection/timeout/quota/429 failures; sleeps 1+2+4+8+16 seconds plus jitter, or larger provider RetryInfo delay. A successful last attempt hides retries in old rows.
- H `src/llm.py:41`: SDK client has no explicit retry/timeout options. SDK retries/network/provider generation can add delay, but actual attempts were not logged. The plateau does not establish an exact timeout policy.
- H `src/llm.py:49-53,68-94,124-127`: optional disk cache, default off; key is model/prompt/temperature/token budget. Hits bypass API/pacing; the old runner does not serialize last_cache_hit. Cache state cannot be inferred reliably from latency alone.
- H `vector_store.py:46-59`: query embeddings are per-query; first index loading is cold, later searches reuse it. Model initialization cannot explain every timed row.

There is no saved successful-call decomposition to attribute the historical 175 seconds precisely. An extra ~1 second for Vector is consistent with retrieval overhead, not a proven attribution. Plain's final rows contain no populated top-level errors; abstentions are not proof of transport errors. A ~175-second adaptive recovery call also appears in the one fallback case.

Today's code differs: `src/systems/base.py:281-285` delegates to harness_v2; `src/evaluation/harness_v2.py:69-121` snapshots configs, controls cache namespaces/repeats and optional warm-up. `src/llm.py:65-75` sets 60,000 ms timeout, SDK attempts=1 and cache_enabled=True; `:105-193` logs attempts/sleeps/cache hits. The config comment still says cache off; actual harness flags matter. These later changes cannot reconstruct old timing.

## 5. Vector RAG configuration and 6.2%

`src/vector_store.py:13-45,68-79`: 1,200-character chunks (not tokens), 180-character overlap after whitespace normalization; default model sentence-transformers/all-MiniLM-L6-v2, overridable via EMBEDDING_MODEL; normalized float32 vectors and FAISS IndexFlatIP. Index file/commit/issue/pull-request metadata plus content/message/body, prefer processed over raw data, include synthetic documents. This is artifact text, not relationship-preserving graph retrieval. `src/systems/vector_rag.py:8-10` hardcodes k=10 and uses the evidence-only prompt. No BM25, learned reranker or graph joins.

**Repository filtering was present.** `vector_rag.py:10` extracts `repository owner/name` and passes repository=repo. Kind filtering exists but is not supplied. Missing that wording causes global search. Historical H@45f8ac56 `vector_store.py:51-58` searches only global top 50 for k=10, then filters, without expansion. It can starve the requested repository. Today's `vector_store.py:113-155` expands candidates, a later fix. The historical index lacks a settings manifest; defaults/current v2 manifests are not proof of its actual embedding build.

Saved outcomes: 15/242 correct=6.1983%, 209 exact “Insufficient repository evidence.” responses, 33 other answers, no populated top-level errors (`results/final_evaluation/vector_rag_results.csv:1`, final summary row 9). `src/systems/prompts.py:12-39` requires abstention if evidence lacks the answer. Plausible contributors: candidate starvation, identifier-heavy questions, list/multi-hop demands exceeding ten chunks, missing relationships, synthesis failures. Their causal shares are unmeasured; a claim that repo filtering was simply missing is false. Validate retrieval recall and tuning on development data.

## 6. Framework baseline implementations

**Both are custom pipelines with library names.** `src/systems/langchain_graphrag.py:1-49` imports project Graph/Gemini/helpers, generates Cypher, executes Graph.query, deduplicates rows and generates an answer. `src/systems/llamaindex_graphrag.py:1-53` does the same with a property-graph preamble and renamed evidence fields. Neither invokes real LangChain graph QA nor LlamaIndex graph/Text2Cypher components. Installed packages do not prove use. Classification: baseline design/reporting flaw; rename them or implement the real components required by `CLAUDE.md:17-18`.

## 7. Faithfulness / unsupported-claim judge

**No Gemini judge generated these scores.** `src/evaluation/metrics.py:655-760` splits claims on sentences/newlines, marks support by bidirectional substring containment or token recall≥0.60 and F1≥0.55. Support is gold required facts + gold evidence + expected entities (`:1454-1469`), not exclusively retrieved context. Supported rate=supported claims/claims. Hallucination rate=capped max(unsupported claims, unsupported extracted entities)/claims; the rates need not be complements in general. `report_tables.py:89-94` renames supported_claim_rate to faithfulness.

This is a lexical gold-support proxy, not an independent entailment judgment. Gemini generates answers/Cypher, not these metric judgments. `src/evaluation/hallucination_annotation.py:123-148` creates blank human-label fields; an annotation template is not a completed judgment study. The saved final sheet has 1,936 rows and zero populated supported-label cells (`results/final_evaluation_metrics/hallucination_annotation.csv:1`). Appendix B prints these exact functions.

## 8. Question/retrieval/router templates and overlap

Seven category generators implement 19 realized template names (`src/benchmark_gen/generate_benchmark.py:432-1615`). The registry has 18 matchers producing those same 19 names because code/documentation share fragment_to_file (`src/systems/query_registry.py:46-383,386-418`). Generator Cypher gets gold from the graph queried by the retriever. Router calls this same registry first with confidence .95 (`src/systems/router.py:96-107`).

Read-only execution of the pure matcher: **300/300 questions match; 242/242 hidden-test match; all 19/19 generated names equal matched registry names.** Development and validation are each 29/29. Appendix E quantifies every template, its source function and hidden-test count. The four “held-out” families are already implemented in the registry: split-level absence from dev does not establish implementation novelty.

Router has ten graph keywords, nine vector keywords and five multi-hop markers (`router.py:46-65`), overlapping generator phrases such as “code fragment”, “contains the text”, “authored commits that modified” and “modified through commits authored by”. All 300 benchmark items bypass these heuristics through registry matches. No registry template routes vector; fragments route hybrid. The vector keyword confidence .55 is below the high threshold .85 and forced hybrid (`router.py:126-151`). Vector is unreachable under default legacy routing. Literal route-label agreement is 171/242=70.66%; the saved 100% metric accepts any route for code/documentation (`metrics.py:1504-1520`).

## 9. Leakage surfaces

| Surface | Evidence and assessment |
|---|---|
| Shared template families | Confirmed 19/19 names, 300/300 matches. The benchmark tests familiar query-family execution, not independent language generalization. |
| Holdout templates | All four already implemented (`query_registry.py:84-99,315-331,351-383`). Template-holdout novelty claim is not supported by implementation separation. |
| Gold metadata | expected_retrieval_route survives stripping (`split_benchmark.py:50-61`); Oracle explicitly reads it (`oracle_hybrid_rag.py:58-76`). Appropriate only as declared oracle privilege; not an outcome maximum. Other legacy answer methods receive question text, so this is not proof they read gold answers. |
| Router heuristics | Generator-language overlap and benchmark-specific comment at `router.py:46-65`; registry bypasses heuristics on all saved template items. |
| Prompt schema | `prompts.py:42-72` exposes schema and alias answer. Legitimate schema provision, but deterministic graph answering versus LLM synthesis changes more than routing. |
| Few-shot examples | No few-shot Q/A examples in legacy answer/Cypher prompts (`prompts.py:12-72`) or wrapper (`retrieval_core.py:106-143`). Do not allege demonstrated few-shot leakage. Later v2 router training is separate. |
| Post-test exposure | Keys coexist with questions; current parser fixes the exact failed hidden-test title (`query_registry.py:237-259`) while saved params remain Can. Confirmed source/result drift and reuse risk, not proof of intentional tuning before the original run. |
| Retrieval corpus | Retrieving the target repository is intended access, not itself leakage. Shared generator/retriever snapshot families and synthetic data affect validity (`vector_store.py:31-44`, `generate_benchmark.py:359-417`). No demonstrated index injection of gold answers. |
| Pretraining | Public-repository pretraining overlap cannot be established or excluded here. `benchmark_gen/leakage_check.py:1-19,92-125` checks context-free answerability, not training-data provenance. |

These findings establish structural dependence and privileged metadata, not intent or every historical data flow. Holding out Airflow from split tuning does not remove the globally coded templates that cover its questions.


## Appendix A. All 242 actual routes

G=graph, V=vector, H=hybrid. O=Oracle, A=Adaptive. Source line columns refer to `results/final_evaluation/oracle_hybrid_rag_results.csv` and `results/final_evaluation/adaptive_hybrid_graphrag_results.csv`. Gold is from `data/benchmark/splits/hidden_test_answer_key.csv`. Lines are physical CSV record starts.

| ID | Gold | O | A | Adaptive fallback | Oracle line | Adaptive line |
|---|---|---|---|---|---:|---:|
| code_retrieval-001 | V | H | H | False | 64 | 64 |
| code_retrieval-002 | V | H | H | False | 324 | 324 |
| code_retrieval-003 | V | H | H | False | 367 | 367 |
| code_retrieval-004 | V | H | H | False | 331 | 331 |
| code_retrieval-005 | V | H | H | False | 429 | 429 |
| code_retrieval-006 | V | H | H | False | 1487 | 1478 |
| code_retrieval-007 | V | H | H | False | 2136 | 2124 |
| code_retrieval-008 | V | H | H | False | 1535 | 1523 |
| code_retrieval-009 | V | H | H | False | 1957 | 1945 |
| code_retrieval-010 | V | H | H | False | 1538 | 1526 |
| code_retrieval-011 | V | H | H | False | 521 | 521 |
| code_retrieval-012 | V | H | H | False | 61 | 61 |
| code_retrieval-013 | V | H | H | False | 2655 | 2640 |
| code_retrieval-014 | V | H | H | False | 1122 | 1116 |
| code_retrieval-015 | V | H | H | False | 2411 | 2399 |
| code_retrieval-016 | V | H | H | False | 2801 | 2786 |
| code_retrieval-017 | V | H | H | False | 1775 | 1763 |
| code_retrieval-018 | V | H | H | False | 973 | 967 |
| code_retrieval-019 | V | H | H | False | 2832 | 2817 |
| code_retrieval-020 | V | H | H | False | 1644 | 1632 |
| code_retrieval-021 | V | H | H | False | 613 | 613 |
| code_retrieval-022 | V | H | H | False | 2550 | 2535 |
| code_retrieval-023 | V | H | H | False | 2283 | 2271 |
| code_retrieval-024 | V | H | H | False | 26 | 26 |
| code_retrieval-025 | V | H | H | False | 1746 | 1734 |
| code_retrieval-026 | V | H | H | False | 8 | 8 |
| code_retrieval-027 | V | H | H | False | 2124 | 2112 |
| code_retrieval-028 | V | H | H | False | 399 | 399 |
| code_retrieval-029 | V | H | H | False | 518 | 518 |
| code_retrieval-030 | V | H | H | False | 1753 | 1741 |
| code_retrieval-031 | V | H | H | False | 2012 | 2000 |
| code_retrieval-032 | V | H | H | False | 2214 | 2202 |
| code_retrieval-033 | V | H | H | False | 1509 | 1497 |
| code_retrieval-034 | V | H | H | False | 413 | 413 |
| code_retrieval-035 | V | H | H | False | 1329 | 1320 |
| code_retrieval-036 | V | H | H | False | 1877 | 1865 |
| code_retrieval-037 | V | H | H | False | 1017 | 1011 |
| code_retrieval-038 | V | H | H | False | 1484 | 1475 |
| code_retrieval-039 | V | H | H | False | 2309 | 2297 |
| code_retrieval-040 | V | H | H | False | 1008 | 1002 |
| dependency_analysis-002 | G | G | G | False | 2 | 2 |
| dependency_analysis-004 | G | G | G | False | 2807 | 2792 |
| dependency_analysis-005 | G | G | G | False | 3211 | 3180 |
| dependency_analysis-006 | G | G | G | False | 2820 | 2805 |
| dependency_analysis-007 | G | G | G | False | 2171 | 2159 |
| dependency_analysis-008 | G | G | G | False | 3239 | 3208 |
| dependency_analysis-010 | G | G | G | False | 572 | 572 |
| dependency_analysis-011 | G | G | G | False | 3202 | 3171 |
| dependency_analysis-012 | G | G | G | False | 29 | 29 |
| dependency_analysis-013 | G | G | G | False | 3236 | 3205 |
| dependency_analysis-014 | G | G | G | False | 634 | 634 |
| dependency_analysis-015 | G | G | G | False | 3207 | 3176 |
| dependency_analysis-016 | G | G | G | False | 533 | 533 |
| dependency_analysis-017 | G | G | G | False | 568 | 568 |
| dependency_analysis-018 | G | G | G | False | 2175 | 2163 |
| dependency_analysis-020 | G | G | G | False | 3197 | 3166 |
| dependency_analysis-021 | G | G | G | False | 3192 | 3161 |
| dependency_analysis-022 | G | G | G | False | 3233 | 3202 |
| dependency_analysis-023 | G | G | G | False | 1227 | 1221 |
| dependency_analysis-024 | G | G | G | False | 3227 | 3196 |
| dependency_analysis-026 | G | G | G | False | 586 | 586 |
| dependency_analysis-027 | G | G | G | False | 23 | 23 |
| dependency_analysis-029 | G | G | G | False | 1763 | 1751 |
| dependency_analysis-031 | G | G | G | False | 966 | 960 |
| dependency_analysis-032 | G | G | G | False | 2826 | 2811 |
| dependency_analysis-034 | G | G | G | False | 3242 | 3211 |
| dependency_analysis-035 | G | G | G | False | 1931 | 1919 |
| dependency_analysis-036 | G | G | G | False | 2197 | 2185 |
| dependency_analysis-037 | G | G | G | False | 1757 | 1745 |
| dependency_analysis-038 | G | G | G | False | 3189 | 3158 |
| dependency_analysis-039 | G | G | G | False | 2184 | 2172 |
| dependency_analysis-040 | G | G | G | False | 11 | 11 |
| dependency_analysis-041 | G | G | G | False | 1291 | 1285 |
| dependency_analysis-044 | G | G | G | False | 1531 | 1519 |
| dependency_analysis-045 | G | G | G | False | 2757 | 2742 |
| developer_activity-001 | G | G | G | False | 868 | 868 |
| developer_activity-002 | G | G | G | False | 416 | 416 |
| developer_activity-003 | G | G | G | False | 2270 | 2258 |
| developer_activity-004 | G | G | G | False | 170 | 170 |
| developer_activity-005 | G | G | G | False | 1939 | 1927 |
| developer_activity-007 | G | G | G | False | 2885 | 2870 |
| developer_activity-008 | G | G | G | False | 2888 | 2873 |
| developer_activity-010 | G | G | G | False | 2876 | 2861 |
| developer_activity-011 | G | G | G | False | 2941 | 2926 |
| developer_activity-012 | G | G | G | False | 2934 | 2919 |
| developer_activity-013 | G | G | G | False | 2296 | 2284 |
| developer_activity-014 | G | G | G | False | 2879 | 2864 |
| developer_activity-016 | G | G | G | False | 2201 | 2189 |
| developer_activity-019 | G | G | G | False | 2835 | 2820 |
| developer_activity-021 | G | G | G | False | 2882 | 2867 |
| developer_activity-024 | G | G | G | False | 2925 | 2910 |
| developer_activity-025 | G | G | G | False | 291 | 291 |
| developer_activity-027 | G | G | G | False | 2838 | 2823 |
| developer_activity-028 | G | G | G | False | 2937 | 2922 |
| developer_activity-030 | G | G | G | False | 2262 | 2250 |
| documentation_lookup-001 | V | H | H | False | 1945 | 1933 |
| documentation_lookup-002 | V | H | H | False | 3045 | 3014 |
| documentation_lookup-003 | V | H | H | False | 3042 | 3011 |
| documentation_lookup-004 | V | H | H | False | 1119 | 1113 |
| documentation_lookup-005 | V | H | H | False | 969 | 963 |
| documentation_lookup-006 | V | H | H | False | 1147 | 1141 |
| documentation_lookup-007 | V | H | H | False | 2823 | 2808 |
| documentation_lookup-008 | V | H | H | False | 1960 | 1948 |
| documentation_lookup-009 | V | H | H | False | 304 | 304 |
| documentation_lookup-010 | V | H | H | False | 1515 | 1503 |
| documentation_lookup-011 | V | H | H | False | 1772 | 1760 |
| documentation_lookup-012 | V | H | H | False | 1450 | 1441 |
| documentation_lookup-013 | V | H | H | False | 2286 | 2274 |
| documentation_lookup-014 | V | H | H | False | 2293 | 2281 |
| documentation_lookup-015 | V | H | H | False | 1150 | 1144 |
| documentation_lookup-016 | V | H | H | False | 1760 | 1748 |
| documentation_lookup-019 | V | H | H | False | 1288 | 1282 |
| documentation_lookup-021 | V | H | H | False | 2181 | 2169 |
| documentation_lookup-022 | V | H | H | False | 5 | 5 |
| documentation_lookup-023 | V | H | H | False | 881 | 881 |
| documentation_lookup-025 | V | H | H | False | 402 | 402 |
| documentation_lookup-026 | V | H | H | False | 1522 | 1510 |
| documentation_lookup-027 | V | H | H | False | 3039 | 3008 |
| documentation_lookup-028 | V | H | H | False | 2117 | 2105 |
| documentation_lookup-029 | V | H | H | False | 58 | 58 |
| documentation_lookup-030 | V | H | H | False | 2652 | 2637 |
| documentation_lookup-031 | V | H | H | False | 1326 | 1317 |
| documentation_lookup-032 | V | H | H | False | 2178 | 2166 |
| documentation_lookup-033 | V | H | H | False | 1294 | 1288 |
| documentation_lookup-034 | V | H | H | False | 1144 | 1138 |
| documentation_lookup-035 | V | H | H | False | 2804 | 2789 |
| issue_pr_analysis-001 | G | G | G | False | 311 | 311 |
| issue_pr_analysis-002 | G | G | G | False | 3002 | 2980 |
| issue_pr_analysis-003 | G | G | G | False | 963 | 3219 |
| issue_pr_analysis-004 | G | G | G | False | 36 | 36 |
| issue_pr_analysis-006 | G | G | G | False | 2944 | 2929 |
| issue_pr_analysis-008 | G | G | G | False | 2965 | 2947 |
| issue_pr_analysis-011 | G | G | G | False | 884 | 3216 |
| issue_pr_analysis-013 | G | G | G | False | 1495 | 3225 |
| issue_pr_analysis-016 | G | G | G | False | 648 | 648 |
| issue_pr_analysis-017 | G | G | G | False | 2958 | 2943 |
| issue_pr_analysis-018 | G | G | G | False | 2537 | 3228 |
| issue_pr_analysis-019 | G | G | G | False | 3005 | 3237 |
| issue_pr_analysis-020 | G | G | G | False | 2114 | 2102 |
| issue_pr_analysis-022 | G | G | G | False | 2955 | 2940 |
| issue_pr_analysis-023 | G | G | G | False | 1942 | 1930 |
| issue_pr_analysis-024 | G | G | G | False | 3014 | 2983 |
| issue_pr_analysis-025 | G | G | G | False | 3008 | 3240 |
| issue_pr_analysis-026 | G | G | G | False | 2952 | 2937 |
| issue_pr_analysis-030 | G | G | G | True | 2971 | 2953 |
| issue_pr_analysis-031 | G | G | G | False | 363 | 363 |
| issue_pr_analysis-032 | G | G | G | False | 3036 | 3005 |
| issue_pr_analysis-034 | G | G | G | False | 3011 | 3243 |
| issue_pr_analysis-037 | G | G | G | False | 1749 | 1737 |
| issue_pr_analysis-038 | G | G | G | False | 272 | 272 |
| issue_pr_analysis-040 | G | G | G | False | 2980 | 2958 |
| issue_pr_analysis-041 | G | G | G | False | 2962 | 3231 |
| issue_pr_analysis-042 | G | G | G | False | 2947 | 2932 |
| issue_pr_analysis-043 | G | G | G | False | 2974 | 2955 |
| issue_pr_analysis-044 | G | G | G | False | 2772 | 2757 |
| issue_pr_analysis-046 | G | G | G | False | 2968 | 2950 |
| issue_pr_analysis-047 | G | G | G | False | 1323 | 3222 |
| issue_pr_analysis-048 | G | G | G | False | 2977 | 3234 |
| multi_hop-001 | H | H | H | False | 1125 | 1119 |
| multi_hop-002 | H | H | H | False | 3123 | 3092 |
| multi_hop-006 | H | H | H | False | 3048 | 3017 |
| multi_hop-007 | H | H | H | False | 3178 | 3147 |
| multi_hop-008 | H | H | H | False | 3054 | 3023 |
| multi_hop-010 | H | H | H | False | 2120 | 2108 |
| multi_hop-011 | H | H | H | False | 3132 | 3101 |
| multi_hop-013 | H | H | H | False | 1222 | 1216 |
| multi_hop-014 | H | H | H | False | 3150 | 3119 |
| multi_hop-018 | H | H | H | False | 1525 | 1513 |
| multi_hop-019 | H | H | H | False | 942 | 939 |
| multi_hop-020 | H | H | H | False | 3130 | 3099 |
| multi_hop-021 | H | H | H | False | 505 | 505 |
| multi_hop-022 | H | H | H | False | 2127 | 2115 |
| multi_hop-023 | H | H | H | False | 3115 | 3084 |
| multi_hop-025 | H | H | H | False | 3134 | 3103 |
| multi_hop-026 | H | H | H | False | 509 | 509 |
| multi_hop-028 | H | H | H | False | 2131 | 2119 |
| multi_hop-030 | H | H | H | False | 524 | 524 |
| multi_hop-033 | H | H | H | False | 2528 | 2516 |
| multi_hop-034 | H | H | H | False | 307 | 307 |
| multi_hop-036 | H | H | H | False | 994 | 988 |
| multi_hop-037 | H | H | H | False | 3118 | 3087 |
| multi_hop-038 | H | H | H | False | 3120 | 3089 |
| multi_hop-039 | H | H | H | False | 1952 | 1940 |
| multi_hop-040 | H | H | H | False | 1948 | 1936 |
| multi_hop-041 | H | H | H | False | 643 | 643 |
| multi_hop-042 | H | H | H | False | 616 | 616 |
| multi_hop-045 | H | H | H | False | 1011 | 1005 |
| multi_hop-046 | H | H | H | False | 3137 | 3106 |
| multi_hop-047 | H | H | H | False | 2193 | 2181 |
| multi_hop-048 | H | H | H | False | 3057 | 3026 |
| multi_hop-049 | H | H | H | False | 3107 | 3076 |
| multi_hop-050 | H | H | H | False | 3050 | 3019 |
| multi_hop-051 | H | H | H | False | 2793 | 2778 |
| multi_hop-052 | H | H | H | False | 2139 | 2127 |
| multi_hop-053 | H | H | H | False | 1490 | 1481 |
| multi_hop-054 | H | H | H | False | 327 | 327 |
| multi_hop-055 | H | H | H | False | 563 | 563 |
| multi_hop-056 | H | H | H | False | 166 | 166 |
| multi_hop-057 | H | H | H | False | 2289 | 2277 |
| multi_hop-058 | H | H | H | False | 514 | 514 |
| multi_hop-059 | H | H | H | False | 1332 | 1323 |
| multi_hop-060 | H | H | H | False | 2810 | 2795 |
| structure-001 | G | G | G | False | 621 | 621 |
| structure-002 | G | G | G | False | 335 | 335 |
| structure-003 | G | G | G | False | 1963 | 1951 |
| structure-004 | G | G | G | False | 1453 | 1444 |
| structure-005 | G | G | G | False | 1898 | 1886 |
| structure-006 | G | G | G | False | 390 | 390 |
| structure-007 | G | G | G | False | 2414 | 2402 |
| structure-008 | G | G | G | False | 2143 | 2131 |
| structure-009 | G | G | G | False | 275 | 275 |
| structure-010 | G | G | G | False | 637 | 637 |
| structure-011 | G | G | G | False | 707 | 707 |
| structure-012 | G | G | G | False | 1336 | 1327 |
| structure-013 | G | G | G | False | 887 | 884 |
| structure-014 | G | G | G | False | 2798 | 2783 |
| structure-015 | G | G | G | False | 555 | 555 |
| structure-016 | G | G | G | False | 1130 | 1124 |
| structure-017 | G | G | G | False | 1232 | 1226 |
| structure-018 | G | G | G | False | 405 | 405 |
| structure-019 | G | G | G | False | 1155 | 1149 |
| structure-020 | G | G | G | False | 542 | 542 |
| structure-021 | G | G | G | False | 652 | 652 |
| structure-022 | G | G | G | False | 2540 | 2525 |
| structure-023 | G | G | G | False | 2217 | 2205 |
| structure-024 | G | G | G | False | 1880 | 1868 |
| structure-025 | G | G | G | False | 315 | 315 |
| structure-026 | G | G | G | False | 1498 | 1486 |
| structure-027 | G | G | G | False | 1298 | 1292 |
| structure-028 | G | G | G | False | 857 | 857 |
| structure-029 | G | G | G | False | 998 | 992 |
| structure-030 | G | G | G | False | 1281 | 1275 |
| structure-031 | G | G | G | False | 1640 | 1628 |
| structure-032 | G | G | G | False | 1141 | 1135 |
| structure-033 | G | G | G | False | 1438 | 1429 |
| structure-034 | G | G | G | False | 798 | 798 |
| structure-035 | G | G | G | False | 538 | 538 |
| structure-036 | G | G | G | False | 2516 | 2504 |
| structure-037 | G | G | G | False | 589 | 589 |
| structure-038 | G | G | G | False | 601 | 601 |
| structure-039 | G | G | G | False | 2760 | 2745 |
| structure-040 | G | G | G | False | 946 | 943 |

Fixed Hybrid recovery evidence: `results/final_evaluation/fixed_hybrid_rag_results.csv:2971`. Oracle and Adaptive citations for the same ID appear above.

## Appendix B. Exact legacy scoring functions

Verbatim current `src/evaluation/metrics.py` (legacy scorer). Regex definitions, functions and metric wiring are included; line ranges identify original source.

`src/evaluation/metrics.py:173-193`

```python
PATH_RE = re.compile(
    r"(?<![\w.-])"
    r"(?:[\w.@+\-]+[\\/])+"
    r"[\w.@+\-]+"
    r"(?:\.[A-Za-z0-9]+)?"
)

ISSUE_RE = re.compile(
    r"(?<!\w)#\d+\b"
)

COMMIT_RE = re.compile(
    r"\b[a-f0-9]{7,40}\b",
    re.I,
)

SYMBOL_RE = re.compile(
    r"[`'\"]"
    r"([A-Za-z_][A-Za-z0-9_.$:< >\-]*)"
    r"[`'\"]"
)
```

`src/evaluation/metrics.py:202-209`

```python
def text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, float) and math.isnan(value):
        return ""

    return str(value).strip()
```

`src/evaluation/metrics.py:212-224`

```python
def norm(value: Any) -> str:
    value_text = text(value).lower()
    value_text = value_text.replace("\\", "/")
    value_text = re.sub(r"\s+", " ", value_text)
    value_text = re.sub(
        r"\s*([:/#=><|])\s*",
        r"\1",
        value_text,
    )

    return value_text.strip(
        " \t\r\n.,;:!?\"'`()[]{}"
    )
```

`src/evaluation/metrics.py:295-311`

```python
def uniq(items: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()

    for item in items:
        normalized = norm(item)

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(normalized)
        output.append(normalized)

    return output
```

`src/evaluation/metrics.py:314-321`

```python
def safe_div(
    numerator: float,
    denominator: float,
) -> float:
    if not denominator:
        return 0.0

    return float(numerator / denominator)
```

`src/evaluation/metrics.py:328-363`

```python
def set_prf(
    expected: Iterable[Any],
    predicted: Iterable[Any],
) -> tuple[float, float, float]:
    expected_set = set(uniq(expected))
    predicted_set = set(uniq(predicted))

    if not expected_set and not predicted_set:
        return 1.0, 1.0, 1.0

    if not expected_set:
        return 0.0, 1.0, 0.0

    if not predicted_set:
        return 0.0, 0.0, 0.0

    overlap = len(
        expected_set & predicted_set
    )

    precision = safe_div(
        overlap,
        len(predicted_set),
    )

    recall = safe_div(
        overlap,
        len(expected_set),
    )

    f1 = safe_div(
        2 * precision * recall,
        precision + recall,
    )

    return precision, recall, f1
```

`src/evaluation/metrics.py:403-423`

```python
def contained(
    answer: str,
    expected_item: str,
) -> bool:
    normalized_answer = norm(answer)
    normalized_item = norm(expected_item)

    if not normalized_item:
        return False

    if normalized_item in normalized_answer:
        return True

    return bool(
        re.search(
            rf"(?<![a-z0-9_])"
            rf"{re.escape(normalized_item)}"
            rf"(?![a-z0-9_])",
            normalized_answer,
        )
    )
```

`src/evaluation/metrics.py:426-454`

```python
def coverage(
    answer: str,
    expected: Iterable[Any],
) -> tuple[float, float, int, int]:
    expected_items = uniq(expected)

    if not expected_items:
        return math.nan, math.nan, 0, 0

    matched = sum(
        contained(answer, item)
        for item in expected_items
    )

    coverage_value = safe_div(
        matched,
        len(expected_items),
    )

    accuracy = float(
        matched == len(expected_items)
    )

    return (
        accuracy,
        coverage_value,
        matched,
        len(expected_items),
    )
```

`src/evaluation/metrics.py:553-576`

```python
def extract_entities(answer: str) -> list[str]:
    found: list[str] = []

    found.extend(
        PATH_RE.findall(answer)
    )

    found.extend(
        ISSUE_RE.findall(answer)
    )

    found.extend(
        COMMIT_RE.findall(answer)
    )

    found.extend(
        item.replace(" ", "")
        for item in SYMBOL_RE.findall(answer)
    )

    return uniq(
        item.rstrip(".,;:!?)]}")
        for item in found
    )
```

`src/evaluation/metrics.py:579-596`

```python
def expected_entities(
    row: pd.Series,
) -> list[str]:
    explicit = flatten(
        row.get("expected_entities")
    )

    if explicit:
        return explicit

    expected_answer = text(
        row.get("expected_answer")
    )

    if expected_answer:
        return flatten(expected_answer)

    return []
```

`src/evaluation/metrics.py:324-325`

```python
def tokens(value: Any) -> list[str]:
    return WORD_RE.findall(norm(value))
```

`src/evaluation/metrics.py:366-400`

```python
def token_prf(
    reference: str,
    prediction: str,
) -> tuple[float, float, float]:
    reference_tokens = Counter(
        tokens(reference)
    )

    prediction_tokens = Counter(
        tokens(prediction)
    )

    overlap = sum(
        (
            reference_tokens
            & prediction_tokens
        ).values()
    )

    precision = safe_div(
        overlap,
        sum(prediction_tokens.values()),
    )

    recall = safe_div(
        overlap,
        sum(reference_tokens.values()),
    )

    f1 = safe_div(
        2 * precision * recall,
        precision + recall,
    )

    return precision, recall, f1
```

`src/evaluation/metrics.py:655-671`

```python
def claims(
    answer: str,
    explicit_claims: Any,
) -> list[str]:
    explicit = flatten(explicit_claims)

    if explicit:
        return explicit

    return [
        sentence.strip()
        for sentence in re.split(
            r"(?<=[.!?])\s+|\n+",
            answer,
        )
        if sentence.strip()
    ]
```

`src/evaluation/metrics.py:674-703`

```python
def claim_supported(
    claim: str,
    support_items: list[str],
) -> bool:
    normalized_claim = norm(claim)

    if not normalized_claim:
        return False

    for support in support_items:
        normalized_support = norm(support)

        if not normalized_support:
            continue

        if (
            normalized_support in normalized_claim
            or normalized_claim in normalized_support
        ):
            return True

        _, recall, f1 = token_prf(
            normalized_support,
            normalized_claim,
        )

        if recall >= 0.60 and f1 >= 0.55:
            return True

    return False
```

`src/evaluation/metrics.py:706-760`

```python
def grounding(
    answer: str,
    explicit_claims: Any,
    support: list[str],
    predicted_entities: list[str],
) -> tuple[float, float, int, int]:
    generated_claims = claims(
        answer,
        explicit_claims,
    )

    if not generated_claims:
        return math.nan, math.nan, 0, 0

    supported_count = sum(
        claim_supported(claim, support)
        for claim in generated_claims
    )

    normalized_support = norm(
        " ".join(support)
    )

    unsupported_entities = sum(
        1
        for entity in predicted_entities
        if norm(entity) not in normalized_support
    )

    unsupported_claims = max(
        len(generated_claims) - supported_count,
        unsupported_entities,
    )

    unsupported_claims = min(
        len(generated_claims),
        unsupported_claims,
    )

    supported_claim_rate = safe_div(
        supported_count,
        len(generated_claims),
    )

    hallucination_rate = safe_div(
        unsupported_claims,
        len(generated_claims),
    )

    return (
        supported_claim_rate,
        hallucination_rate,
        supported_count,
        len(generated_claims),
    )
```

`src/evaluation/metrics.py:1333-1417` (wiring):

```python
def evaluate_row(
    row: pd.Series,
    system: str,
    k: int,
) -> dict[str, Any]:
    answer = text(row.get("answer"))
    reference = text(
        row.get("expected_answer")
    )
    error = text(row.get("error"))

    expected_entity_values = expected_entities(
        row
    )

    predicted_entity_values = (
        flatten(row.get("predicted_entities"))
        or extract_entities(answer)
    )

    required_fact_values = flatten(
        row.get("required_facts")
    )

    # A benchmark may omit a separate required_facts column. In that case,
    # use the validated reference answer (or explicit expected entities) so the
    # metric remains defined and comparable across all systems.
    if not required_fact_values:
        if reference:
            required_fact_values = [reference]
        else:
            required_fact_values = list(expected_entity_values)

    expected_relation_values = relations(
        row.get("expected_relations")
    )

    predicted_relation_values = relations(
        row.get("predicted_relations")
    )

    expected_path_values = flatten(
        row.get("expected_path")
    )

    predicted_path_values = flatten(
        row.get("predicted_path")
    )

    gold_evidence_values = flatten(
        row.get("gold_evidence")
    )

    retrieved_evidence_values = flatten(
        row.get("retrieved_evidence")
    )

    (
        answer_accuracy,
        ground_truth_coverage,
        matched_entities,
        expected_entity_count,
    ) = coverage(
        answer,
        expected_entity_values,
    )

    (
        entity_precision,
        entity_recall,
        entity_f1,
    ) = set_prf(
        expected_entity_values,
        predicted_entity_values,
    )

    (
        required_fact_coverage,
        matched_fact_count,
        required_fact_count,
    ) = fact_coverage(
        answer,
        required_fact_values,
    )

```

## Appendix C. Five concrete accuracy=1, precision=0 examples

All are saved Adaptive answers; long lists are explicitly excerpted. Full text is in the cited raw and metric records. Precision, recall and F1 values below are the saved values, not substituted v2 scores.

### multi_hop-056

Question: Which developers authored commits that modified the file 'flux/www/templates/admin/chart.html' in repository apache/airflow?

Answer:
```text
email:maximebeauchemin@gmail.com
```

Gold:
```text
["email:maximebeauchemin@gmail.com"]
```

Extracted predictions (0 unique):
```json
[]
```

Accuracy=1.0; entity precision=0.0, recall=0.0, F1=0.0. Evidence: `results/final_evaluation_metrics/per_question_metrics.csv:144` and `results/final_evaluation/adaptive_hybrid_graphrag_results.csv:166`.

### multi_hop-034

Question: Which developers authored commits that modified the file 'src/HybridApp/Components/Pages/Catalog/Catalog.razor.css' in repository dotnet/eShop?

Answer:
```text
email:adityam@microsoft.com
```

Gold:
```text
["email:adityam@microsoft.com"]
```

Extracted predictions (0 unique):
```json
[]
```

Accuracy=1.0; entity precision=0.0, recall=0.0, F1=0.0. Evidence: `results/final_evaluation_metrics/per_question_metrics.csv:271` and `results/final_evaluation/adaptive_hybrid_graphrag_results.csv:307`.

### issue_pr_analysis-030

Question: What is the issue number for 'Can't find API Getway project' in repository dotnet/eShop?

Answer:
```text
475
```

Gold:
```text
["475"]
```

Extracted predictions (0 unique):
```json
[]
```

Accuracy=1.0; entity precision=0.0, recall=0.0, F1=0.0. Evidence: `results/final_evaluation_metrics/per_question_metrics.csv:2520` and `results/final_evaluation/adaptive_hybrid_graphrag_results.csv:2953`.

### developer_activity-025

Question: Who are the top commit authors in repository apache/airflow? Return each developer identifier with the number of commits.

Answer:
```text
email:maximebeauchemin@gmail.com | 560
email:maxime.beauchemin@airbnb.com | 267
email:arthur.wiedmer@gmail.com | 31
email:artwr@users.noreply.github.com | 19
email:kerzhner@yahoo-inc.com | 17
email:krishna.puttaswamy@airbnb.com | 14
email:gtoonstra@gmail.com | 10
email:aaron.s.keys@gmail.com | 9
email:krishnaprasad.pn@gmail.com | 8
email:cpeter9@gmail.com | 7
```

Gold:
```text
["email:maximebeauchemin@gmail.com | 560", "email:maxime.beauchemin@airbnb.com | 267", "email:arthur.wiedmer@gmail.com | 31", "email:artwr@users.noreply.github.com | 19", "email:kerzhner@yahoo-inc.com | 17", "email:krishna.puttaswamy@airbnb.com | 14", "email:gtoonstra@gmail.com | 10", "email:aaron.s.keys@gmail.com | 9", "email:krishnaprasad.pn@gmail.com | 8", "email:cpeter9@gmail.com | 7"]
```

Extracted predictions (0 unique):
```json
[]
```

Accuracy=1.0; entity precision=0.0, recall=0.0, F1=0.0. Evidence: `results/final_evaluation_metrics/per_question_metrics.csv:260` and `results/final_evaluation/adaptive_hybrid_graphrag_results.csv:291`.

### developer_activity-004

Question: Which commits were authored by developer email:maximebeauchemin@gmail.com in repository apache/airflow?

Answer:
```text
apache/airflow:commit:8a5bb70fc2808434f50aa864535db225bd85f463
apache/airflow:commit:bdbfe3014b3d60a5be89bee5ce5aaf0d32c440f1
apache/airflow:commit:3adc1de104bafb06d7fe99876e79b1a07487d1d0
apache/airflow:commit:c55c7dd8c3955384344e7b76d907e2e294d53dcb
apache/airflow:commit:f76b7fef380b90555a337498624b8dc31cc9e582
apache/airflow:commit:10fc555333dba8c1616da1d6d827079cb927048a
apache/airflow:commit:165927f19fd55bae542b3eda2a1bffbd140b6756
apache/airflow:commit:605c169d5f63c7c539c12967f8152513bcb13d53
apache/airflow:commit:15fa33f92eca9f47573e19fbbbe55ea50b933def
apache/airflow:commit:1258dbd6602151e130ae05e56e068eec4260af16
apache/airflow:commit:8946ee3cfc32f3aae5240a84c5047b5b664f4a84
apache/airflow:commit:e0756dad090ee8c2de0d357239c8f9dfb2a644c3
apache/airflow:commit:bc9debe28cf261942c78ae [EXCERPT; remainder omitted]
```

Gold:
```text
["apache/airflow:commit:8a5bb70fc2808434f50aa864535db225bd85f463", "apache/airflow:commit:bdbfe3014b3d60a5be89bee5ce5aaf0d32c440f1", "apache/airflow:commit:3adc1de104bafb06d7fe99876e79b1a07487d1d0", "apache/airflow:commit:c55c7dd8c3955384344e7b76d907e2e294d53dcb", "apache/airflow:commit:f76b7fef380b90555a337498624b8dc31cc9e582", "apache/airflow:commit:10fc555333dba8c1616da1d6d827079cb927048a", "apache/airflow:commit:165927f19fd55bae542b3eda2a1bffbd140b6756", "apache/airflow:commit:605c169d5f63c7c539c12967f8152513bcb13d53", "apache/airflow:commit:15fa33f92eca9f47573e19fbbbe55ea50b933def", "apache/airflow:commit:1258dbd6602151e130ae05e56e068eec4260af16", "apache/airflow:commit:8946ee3cfc32f3aae5240a84c5047b5b664f4a84", "apache/airflow:commit:e0756dad090ee8c2de0d357239c8f9dfb2a644c3", "apache [EXCERPT; remainder omitted]
```

Extracted predictions (101 unique):
```json
["apache/airflow", "8a5bb70fc2808434f50aa864535db225bd85f463", "bdbfe3014b3d60a5be89bee5ce5aaf0d32c440f1", "3adc1de104bafb06d7fe99876e79b1a07487d1d0", "c55c7dd8c3955384344e7b76d907e2e294d53dcb", "f76b7fef380b90555a337498624b8dc31cc9e582", "10fc555333dba8c1616da1d6d827079cb927048a", "165927f19fd55bae542b3eda2a1bffbd140b6756", "605c169d5f63c7c539c12967f8152513bcb13d53", "15fa33f92eca9f47573e19fbbbe55ea50b933def", "1258dbd6602151e130ae05e56e068eec4260af16", "8946ee3cfc32f3aae5240a84c5047b5b664f4a84", "e0756dad090ee8c2de0d357239c8f9dfb2a644c3", "bc9debe28cf261942c78ae44a6d027b8d5a842f7", "1f63fdac9c7c264d46cebba985e95e4b7d1670f9", "c84b64976a1ac9334c03e83e75e2606d7a74ae60", "333e1240889778596dca2f18260cf2b6a77ce366", "03eb7ed44a97137b171500ef05a825f32070c7a5", "9368c719fccb246dfaa396fea2c592d5 [EXCERPT; remainder omitted]
```

Accuracy=1.0; entity precision=0.0, recall=0.0, F1=0.0. Evidence: `results/final_evaluation_metrics/per_question_metrics.csv:145` and `results/final_evaluation/adaptive_hybrid_graphrag_results.csv:170`.

## Appendix D. Complete saved legacy aggregate-table inventory

Raw answers/per-question metrics, empty error reports and annotation input sheets are evidence inputs, not aggregate tables. This inventory covers legacy results outside results/v2; later phase reports describe separate runs. The supplied score pair belongs to final_evaluation_metrics.

| Table file | True population | Evidence |
|---|---|---|
| `results/ablations/fixed_1hop/evaluation/summary_metrics.csv` | 29 development questions/variant; not test | `results/ablations/fixed_1hop/evaluation/summary_metrics.csv:1` |
| `results/ablations/fixed_2hop/evaluation/summary_metrics.csv` | 29 development questions/variant; not test | `results/ablations/fixed_2hop/evaluation/summary_metrics.csv:1` |
| `results/ablations/fixed_3hop/evaluation/summary_metrics.csv` | 29 development questions/variant; not test | `results/ablations/fixed_3hop/evaluation/summary_metrics.csv:1` |
| `results/ablations/full_system/evaluation/summary_metrics.csv` | 29 development questions/variant; not test | `results/ablations/full_system/evaluation/summary_metrics.csv:1` |
| `results/ablations/fusion_equal_weight/evaluation/summary_metrics.csv` | 29 development questions/variant; not test | `results/ablations/fusion_equal_weight/evaluation/summary_metrics.csv:1` |
| `results/ablations/fusion_graph_heavy/evaluation/summary_metrics.csv` | 29 development questions/variant; not test | `results/ablations/fusion_graph_heavy/evaluation/summary_metrics.csv:1` |
| `results/ablations/fusion_vector_heavy/evaluation/summary_metrics.csv` | 29 development questions/variant; not test | `results/ablations/fusion_vector_heavy/evaluation/summary_metrics.csv:1` |
| `results/ablations/no_fallback/evaluation/summary_metrics.csv` | 29 development questions/variant; not test | `results/ablations/no_fallback/evaluation/summary_metrics.csv:1` |
| `results/ablations/no_graph/evaluation/summary_metrics.csv` | 29 development questions/variant; not test | `results/ablations/no_graph/evaluation/summary_metrics.csv:1` |
| `results/ablations/no_routing/evaluation/summary_metrics.csv` | 29 development questions/variant; not test | `results/ablations/no_routing/evaluation/summary_metrics.csv:1` |
| `results/ablations/no_templates/evaluation/summary_metrics.csv` | 29 development questions/variant; not test | `results/ablations/no_templates/evaluation/summary_metrics.csv:1` |
| `results/ablations/no_validation/evaluation/summary_metrics.csv` | 29 development questions/variant; not test | `results/ablations/no_validation/evaluation/summary_metrics.csv:1` |
| `results/ablations/no_vector/evaluation/summary_metrics.csv` | 29 development questions/variant; not test | `results/ablations/no_vector/evaluation/summary_metrics.csv:1` |
| `results/final_evaluation_metrics/report_tables/category_breakdown.csv` | 242 hidden-test questions/system, 8 systems; category/depth cells use Section 3 counts | `results/final_evaluation_metrics/report_tables/category_breakdown.csv:1` |
| `results/final_evaluation_metrics/report_tables/failure_analysis.csv` | 242 hidden-test questions/system, 8 systems; category/depth cells use Section 3 counts | `results/final_evaluation_metrics/report_tables/failure_analysis.csv:1` |
| `results/final_evaluation_metrics/report_tables/main_performance.csv` | 242 hidden-test questions/system, 8 systems; category/depth cells use Section 3 counts | `results/final_evaluation_metrics/report_tables/main_performance.csv:1` |
| `results/final_evaluation_metrics/report_tables/reasoning_depth_breakdown.csv` | 242 hidden-test questions/system, 8 systems; category/depth cells use Section 3 counts | `results/final_evaluation_metrics/report_tables/reasoning_depth_breakdown.csv:1` |
| `results/final_evaluation_metrics/statistical_tests.csv` | 242 hidden-test questions/system, 8 systems; category/depth cells use Section 3 counts; actual paired denominator in each n cell | `results/final_evaluation_metrics/statistical_tests.csv:1` |
| `results/final_evaluation_metrics/summary_metrics.csv` | 242 hidden-test questions/system, 8 systems; category/depth cells use Section 3 counts | `results/final_evaluation_metrics/summary_metrics.csv:1` |
| `results/pilot_evaluation_v2/summary_metrics.csv` | 7 pilot questions/system, 5 systems | `results/pilot_evaluation_v2/summary_metrics.csv:1` |
| `results/regression_eval/report_tables/category_breakdown.csv` | 7 pilot questions/system; subgroups use their own n | `results/regression_eval/report_tables/category_breakdown.csv:1` |
| `results/regression_eval/report_tables/failure_analysis.csv` | 7 pilot questions/system; subgroups use their own n | `results/regression_eval/report_tables/failure_analysis.csv:1` |
| `results/regression_eval/report_tables/main_performance.csv` | 7 pilot questions/system; subgroups use their own n | `results/regression_eval/report_tables/main_performance.csv:1` |
| `results/regression_eval/report_tables/reasoning_depth_breakdown.csv` | 7 pilot questions/system; subgroups use their own n | `results/regression_eval/report_tables/reasoning_depth_breakdown.csv:1` |
| `results/regression_eval/statistical_tests.csv` | 7 pilot questions/system; subgroups use their own n; actual paired denominator in each n cell | `results/regression_eval/statistical_tests.csv:1` |
| `results/regression_eval/summary_metrics.csv` | 7 pilot questions/system; subgroups use their own n | `results/regression_eval/summary_metrics.csv:1` |
| `results/routing_existing_audit/proposed_primary_comparisons.csv` | 242 hidden-test questions; graph/vector/hybrid supports 127/71/44 | `results/routing_existing_audit/proposed_primary_comparisons.csv:1` |
| `results/routing_existing_audit/routing_confusion.csv` | 242 hidden-test questions; graph/vector/hybrid supports 127/71/44 | `results/routing_existing_audit/routing_confusion.csv:1` |
| `results/routing_existing_audit/routing_per_class.csv` | 242 hidden-test questions; graph/vector/hybrid supports 127/71/44 | `results/routing_existing_audit/routing_per_class.csv:1` |
| `results/routing_existing_audit/statistical_tests.csv` | 242 hidden-test questions; graph/vector/hybrid supports 127/71/44; actual paired denominator in each n cell | `results/routing_existing_audit/statistical_tests.csv:1` |
| `results/routing_existing_audit/summary_metrics.csv` | 242 hidden-test questions; graph/vector/hybrid supports 127/71/44 | `results/routing_existing_audit/summary_metrics.csv:1` |
| `results/sanity_check_partial/summary_metrics.csv` | 242 hidden-test questions/system, 4 systems | `results/sanity_check_partial/summary_metrics.csv:1` |
| `results/scalability.csv` | 0 benchmark questions; 2 sizes, 5 timed repeats/query shape/size | `results/scalability.csv:1` |
| `results/statistical_tests.csv` | Mixed sources/repeats, 244 distinct IDs overall; system usable counts below; actual paired denominator in each n cell | `results/statistical_tests.csv:1` |
| `results/summary_metrics.csv` | Mixed sources/repeats, 244 distinct IDs overall; system usable counts below | `results/summary_metrics.csv:1` |

### Mixed root summary population

| System | Raw records | Distinct question IDs | Successful/scored records |
|---|---:|---:|---:|
| adaptive_hybrid_graphrag | 498 | 244 | 14 |
| fixed_graph_rag | 491 | 244 | 7 |
| fixed_hybrid_rag | 491 | 244 | 7 |
| langchain_graphrag | 256 | 244 | 14 |
| llamaindex_graphrag | 263 | 244 | 21 |
| oracle_hybrid_rag | 491 | 244 | 7 |
| plain_llm | 256 | 244 | 14 |
| vector_rag | 256 | 244 | 14 |

Evidence: `results/summary_metrics.csv:2-9`, `results/per_question_metrics.csv:1`. Successful records include repeats and are not a unique test population. Root plot generation reads this summary (`src/evaluation/plots.py:3-5`); saved-image provenance remains unverified. Final statistical overall n=242; all distinct paired n values in that file are 14, 20, 31, 32, 35, 40, 44, 184, 242 (including difficulty/other subgroups). Regression paired n values are 1, 6, 7. Root mixed statistical paired n values are 1, 2, 6, 7, 8, 9, 13, 14, 20, 28, 31, 32, 33, 35, 38, 40, 45, 178, 185, 236, 244. Each row identifies its subgroup and actual n; table row counts are not question counts.

## Appendix E. Quantified template overlap

Every row below has matched count equal to full-pool count, with the matched template_name equal to the generated name. Generator lines locate its template_name assignment; registry lines locate the corresponding matcher definition.

| Template | Full n | Test n | Generator line | Registry matcher/line | Matched full n |
|---|---:|---:|---:|---|---:|
| closed_issue_titles | 5 | 3 | 1125 | `closed_issue_titles` / 280 | 5 |
| code_fragment_to_file | 40 | 40 | 562 | `fragment_to_file` / 63 | 40 |
| commits_modifying_file | 25 | 15 | 630 | `commits_modifying_file` / 161 | 25 |
| developer_commits_in_repository | 24 | 14 | 1482 | `developer_commits` / 123 | 24 |
| developers_modifying_file | 29 | 29 | 1552 | `developers_modifying_file` / 369 | 29 |
| directory_extension_files | 40 | 40 | 493 | `directory_extension_files` / 46 | 40 |
| documentation_fragment_to_file | 35 | 31 | 753 | `fragment_to_file` / 63 | 35 |
| files_modified_by_commit | 20 | 20 | 684 | `files_modified_by_commit` / 84 | 20 |
| files_modified_by_developer | 31 | 15 | 1613 | `files_modified_by_developer` / 144 | 31 |
| highest_numbered_open_issue | 4 | 2 | 1179 | `highest_numbered_open_issue` / 297 | 4 |
| issue_details | 3 | 1 | 1364 | `issue_details` / 220 | 3 |
| issue_number_by_title | 7 | 6 | 959 | `issue_number_by_title` / 237 | 7 |
| issue_state_by_number | 7 | 4 | 899 | `issue_state_by_number` / 203 | 7 |
| issue_title_by_number | 6 | 5 | 840 | `issue_title_by_number` / 186 | 6 |
| issues_matching_title_fragment | 6 | 4 | 1303 | `issues_matching_title_fragment` / 333 | 6 |
| lowest_numbered_open_issue | 2 | 2 | 1233 | `lowest_numbered_open_issue` / 315 | 2 |
| open_issue_titles | 4 | 2 | 1073 | `open_issue_titles` / 263 | 4 |
| repository_for_issue | 6 | 3 | 1021 | `repository_for_issue` / 101 | 6 |
| top_repository_contributors | 6 | 6 | 1428 | `top_repository_contributors` / 351 | 6 |

Evidence inputs: `data/benchmark/benchmark_300.csv:1`, `data/benchmark/splits/hidden_test_answer_key.csv:1`; matcher dispatch `src/systems/query_registry.py:409-414`. This quantifies structural coverage, not exact Cypher-text identity or independent semantic generalization.

Acceptance: nine questions answered with source/artifact evidence; exact scoring functions, five concrete examples, all 242 Oracle routes, and legacy table/figure populations included. No code modified; only AUDIT.md created.

## Prioritized fix list

1. **P0 ? Repair the oracle comparison.** Share retrieval, validation, fallback, fusion and answering across policies. Define a cached outcome oracle including the exact Adaptive output; assert its score cannot fall below Adaptive under the declared metric. Retain all evidence/candidates and label privileges.
2. **P0 ? Freeze a new evaluation protocol/population.** Separate template, paraphrase and independently written human sets; enforce template-family novelty where claimed and keep Airflow out of development. Post-test fixes require a new freeze and affected reruns; the already-inspected 242 questions are not fresh unseen data.
3. **P0 ? Correct scoring semantics.** Replace containment ?accuracy? with a declared answer-type rubric, consistent typed entities, extra-entity/contradiction checks and independently reviewed examples. Preserve old metrics under legacy names and transparently rescore; do not edit gold to improve results.
4. **P0 ? Establish latency provenance.** Validate/use v2 attempt/stage telemetry; record config/model/index hashes, sleeps, cache hits, warm-up, failures and repeat policy. Keep all attempted questions. Historical 175-second attribution remains unresolved.
5. **P1 ? Implement real framework baselines or rename custom pipelines.** Verify actual component calls and match corpora/budgets/settings. Current answer temperature is 0.0 (`prompts.py:9`), whereas CLAUDE.md requires 0.2; resolve before the new freeze.
6. **P1 ? Tune Vector RAG on development data.** Verify progressive candidate filtering, stable repo scoping, index/model provenance, chunk/k selection and lexical retrieval. Measure gold-evidence recall separately from synthesis.
7. **P1 ? Rename/replace lexical faithfulness.** Use validated evidence-grounded human/model judgments with saved judge prompt/model/version and agreement checks. Do not label the old judge Gemini.
8. **P1 ? Rebuild all final tables/figures from one pinned manifest.** Print question/system/repeat and subgroup denominators. Separate 29-question dev ablations, seven-question pilot, mixed root figures and synthetic scalability. Regenerate the heatmap with traceable inputs.
9. **P2 ? Make ablations exercise their mechanisms.** Ensure vector routing is reachable, test real fallback cases, and verify deterministic graph answers do not bypass the fusion/hop component being ablated. Disclose template overlap and post-test exposure.

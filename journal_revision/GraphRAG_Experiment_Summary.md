# Adaptive Hybrid GraphRAG: Experiment Summary

Prepared 3 October 2026 | Retrospective account of the saved experiment

## 1. Overview and main finding

This experiment studies how to answer questions about software repositories using a language model together with repository evidence. It compares no retrieval, semantic vector retrieval, structured graph retrieval, fixed combinations of both, and an adaptive method that selects a retrieval strategy according to the question.

The completed historical evaluation contains eight systems answering the same 242 hidden-test questions, producing 1,936 saved outputs. Adaptive Hybrid GraphRAG and Fixed Hybrid RAG both achieved 234/242, or 96.69%, on the saved answer-accuracy measure. Adaptive recorded a mean response time of 1.070 seconds, compared with 1.515 seconds for fixed hybrid, approximately 29.4% lower. Fixed graph was faster still, at 0.210 seconds, and passed one fewer question.

These are promising results for structured, template-based repository question answering. They are not yet evidence of 96.69% independently validated semantic correctness. The saved accuracy measure checks whether expected entities occur in an answer, and all 242 adaptive answers were marked as deterministic graph answers. The experiment therefore demonstrates a strong graph-query workflow on this benchmark, while the separate benefits of adaptive routing and language-model generation remain incompletely isolated.

This document explains the project from its motivation through its pipeline, design, results, and current limitations. It summarizes local artifacts; no new inference, graph rebuild, or experimental rerun was performed. The sequence below is the methodological sequence, not a reconstructed execution timeline: complete historical execution dates and freezes are not established by the saved files.

## 2. Why the experiment was designed

A developer may need to identify a file, follow dependencies, connect an issue to a pull request, or find contributors responsible for a change. A language model without repository access may lack the exact facts. Vector retrieval searches for semantically similar text, but similarity alone may not recover explicit relationships across several artifacts. A property graph stores those relationships directly and can answer structured queries.

The proposed idea is to combine both evidence sources and choose between them as needed. A graph route can serve exact relationship questions; a vector route can supply relevant text; a hybrid route can combine them. The experiment asks whether this approach improves answer quality and the quality–latency trade-off, which task categories benefit, and whether performance holds across repositories and graph sizes.

Here, GraphRAG means retrieval over a repository property graph. The implemented study is centered on files, commits, developers, issues, pull requests, and their relationships.

## 3. Data collection and preparation

Five real repositories were mined: Spring Petclinic, OpenMRS Core, .NET eShop, Apache Airflow, and MLflow. A synthetic repository, synthetic-org/platform, supplements the real material. Mining collects repository files and development artifacts such as commits, issues, pull requests, and developer identities, subject to configured limits; it is not an exhaustive archive of every project's history.

The preparation sequence is: clone repositories; record repository snapshots and metadata; mine artifacts; preprocess and normalize records; construct the graph; validate its structure; and create the vector index. Repository metadata records exact commit hashes and collection information in data/metadata/. Synthetic relationships and identifiers are generated first; Ollama is intended only to phrase synthetic text and optional question paraphrases, not to determine gold answers.

The saved graph validation report contains 37,780 nodes across six labels:

| Node type | Count |
|---|---|
| File | 27,624 |
| Commit | 5,696 |
| Developer | 1,807 |
| PullRequest | 1,506 |
| Issue | 1,141 |
| Repository | 6 |

Relationships connect repositories to files, commits, issues, and pull requests, and connect developers and changes to relevant artifacts. For example, MODIFIED_FILE links commits to files and AUTHORED_COMMIT links developers to commits. Validation checks include missing relationships, malformed dates, and identity problems. Structural validation does not by itself establish that every mined fact is complete or source-correct.

The parallel vector representation uses SentenceTransformers embeddings and FAISS. The global environment manifest records sentence-transformers/all-MiniLM-L6-v2. Current configuration specifies 1,200-character chunks with 180-character overlap and a top-k setting of 10. These are character counts, not token counts. The vector baseline also hard-codes k=10, so changing configuration alone would not tune that baseline.

## 4. Benchmark and experimental split

The benchmark contains 300 generated questions. Fixed, human-authored Cypher templates are executed against the graph to produce reference answers; the language model does not generate the gold facts. This makes answers reproducible relative to the graph, but also closely couples the benchmark to the graph representation and template mechanisms.

| Split | Questions | Intended purpose |
|---|---|---|
| Development | 29 | Develop and tune the method |
| Validation | 29 | Check tuning decisions |
| Hidden test | 242 | Final comparison after freezing |
| Total | 300 | All benchmark questions |

The full benchmark allocates 40 questions to structure, 40 to code retrieval, 45 to dependency analysis, 35 to documentation lookup, 50 to issue/PR analysis, 30 to developer activity, and 60 to multi-hop tasks.

The split combines repository holdout, template holdout, and category-stratified sampling. The hidden test consists of 136 Airflow questions, 48 additional template-holdout questions outside Airflow, and 58 questions from the remainder. The remaining 58 benchmark questions are the 29 development and 29 validation questions; they were not discarded.

Neither development nor validation contains structure or code-retrieval questions, and each contains only two documentation questions. This limits balanced tuning. In addition, the current query registry recognizes all 242 hidden questions, so template holdout at the dataset level does not demonstrate that the current implementation faces unseen query forms. The historical order of implementation and freezing is unresolved.

Approximately 20 unanswerable probes were planned separately, but their artifact is absent. They must not be counted among the 300 questions or presented as an evaluated negative test set.

## 5. The eight compared systems

| System | How it answers |
|---|---|
| Plain LLM | Uses the model without repository retrieval. |
| Vector RAG | Retrieves semantically similar text chunks before answering. |
| LangChain-labelled pipeline | Uses a custom language-model-to-Cypher graph query pipeline. |
| LlamaIndex-labelled pipeline | Uses another custom property-graph/NL-to-Cypher pipeline. |
| Fixed graph | Uses registered graph-query templates; abstains if unsupported. |
| Fixed hybrid | Retrieves graph and vector evidence for every question. |
| Oracle-labelled hybrid | Uses expected-route labels; intended as a routing reference. |
| Adaptive hybrid | Routes questions, uses graph templates and fallbacks, validates evidence, and produces an answer. |

The LangChain and LlamaIndex names are historical labels in the result files. The inspected system modules implement custom direct pipelines rather than calling those frameworks. Their scores should not be treated as evaluations of the entire frameworks.

The oracle is not a deployable system because it uses gold route information. It also has different execution behavior, so its current score is not a mathematical ceiling on adaptive performance.

## 6. How the adaptive system works

The runtime flow is: question → rule-based routing → graph/vector retrieval → evidence validation and fusion → direct graph answer or grounded language-model answer.

The router uses template matches and other question signals. A template match receives confidence 0.95; other signals receive discrete scores. Configured thresholds are 0.85 for high confidence and 0.60 for medium confidence. These are heuristic scores, not calibrated probabilities. The intended policy favors a selected source for high confidence and combined evidence for more uncertain cases; actual interventions must be verified in traces before interpreting threshold changes experimentally.

Graph retrieval first attempts registered Cypher templates. Fallback paths can use LLM-generated Cypher and vector evidence. Generated queries are checked for read-only operations. Retrieved evidence can be validated, ranked, combined, and truncated. Current adaptive settings include vector top-k 10, at most 100 graph rows, and at most 16 final evidence items. Fusion weights are 0.72 for retrieval score, 0.20 for lexical score, and 0.08 for a graph bonus.

The system may return graph-derived values directly instead of asking the model to rewrite them. In the final saved adaptive run, every answer is labelled deterministic_graph. This shortcut is central to interpreting its speed. It does not prove zero model calls, because fallback Cypher generation can still call a model. Direct answers can use graph rows beyond the final fused evidence list, so retrieval metrics may not describe the full answer-support set.

The design intends shared answer prompts and generation settings for model-generated answers. Current configuration includes a deterministic temperature of 0.0, a 1,024-token answer budget, and a 700-token Cypher budget. A global manifest names gemini-3.1-flash-lite-preview, but per-result model identifiers are absent; the manifest alone cannot establish the model used for every historical output.

## 7. How performance was measured

The coherent final population is results/final_evaluation/ with metrics in results/final_evaluation_metrics/. Every system has the same 242 question IDs. All summary rows report 242 successful runner records and zero error rows. A successful record means execution produced a saved result; it does not mean the answer was correct or non-abstaining.

The principal saved measures are answer accuracy, entity precision/recall/F1, retrieval scores, answer coverage, graph/path proxies, lexical support proxies, and total response latency. Their interpretation matters:

- **Saved answer accuracy:** all expected entities are contained in normalized answer text. Additional wrong entities or contradictions need not cause failure. This document calls it expected-entity containment.
- **Entity F1:** balances extracted entity precision and recall. It uses a different extraction procedure, which helps explain why high containment can coexist with a much lower F1.
- **Answer coverage:** measures non-abstaining responses, separately from correctness.
- **Latency:** wall time around answering, potentially including client pacing, retries, graph/vector work, and generation. It is not pure retrieval or model-service time.
- **Hallucination/support fields:** automated lexical proxies, not completed human factuality judgments.

## 8. Overall results obtained

| System | Containment passes / 242 | Containment % | Entity F1 | Mean time (s) |
|---|---|---|---|---|
| Adaptive hybrid | 234 | 96.69 | 0.5135 | 1.070 |
| Fixed hybrid | 234 | 96.69 | 0.5135 | 1.515 |
| Fixed graph | 233 | 96.28 | 0.5135 | 0.210 |
| Oracle-labelled hybrid | 233 | 96.28 | 0.5135 | 0.312 |
| LangChain-labelled pipeline | 155 | 64.05 | 0.4232 | 16.964 |
| LlamaIndex-labelled pipeline | 154 | 63.64 | 0.4296 | 16.976 |
| Vector RAG | 15 | 6.20 | 0.0528 | 177.586 |
| Plain LLM | 0 | 0.00 | 0.0000 | 95.080 |

Adaptive and fixed hybrid tie on containment and Entity F1. Their recorded mean latency difference is 0.445 seconds, a 29.4% reduction relative to fixed hybrid. The adaptive median is 0.289 seconds versus 0.335 seconds for fixed hybrid; medians and means should not be mixed.

Fixed graph passes 233 questions, one fewer than adaptive, while recording the lowest mean latency. Therefore the result does not establish adaptive as the best choice for every quality–latency requirement. Its gain over the simple template-only baseline is small on this benchmark.

The custom NL-to-Cypher pipelines pass 155 and 154 questions respectively. Vector RAG passes 15 and Plain LLM passes none under the saved metric. Plain LLM abstains on 241/242 questions; Vector RAG abstains on 209/242. Those outcomes demonstrate weakness in these saved configurations on this benchmark, not universal inability of language models or vector retrieval to support repository tasks.

The very large plain/vector mean times must not be interpreted as graph retrieval being intrinsically that much faster. Answer mode, client pacing, retry exposure, execution order, and provider conditions are not separated sufficiently in the logs.

## 9. Results by question category and repository

The following percentages use the same historical containment measure:

| Category | Test n | Adaptive % | Fixed hybrid % | Vector % |
|---|---|---|---|---|
| Structure | 40 | 100.00 | 100.00 | 0.00 |
| Code Retrieval | 40 | 80.00 | 80.00 | 5.00 |
| Dependency Analysis | 35 | 100.00 | 100.00 | 0.00 |
| Documentation Lookup | 31 | 100.00 | 100.00 | 12.90 |
| Issue Pr Analysis | 32 | 100.00 | 100.00 | 28.12 |
| Developer Activity | 20 | 100.00 | 100.00 | 0.00 |
| Multi Hop | 44 | 100.00 | 100.00 | 0.00 |

Adaptive passes every question outside code retrieval and 32/40 code-retrieval questions. All eight adaptive containment failures are in Airflow code retrieval. The audit identifies quoted-fragment parsing problems: nested quotes in code snippets can cause the parser to extract punctuation rather than the intended fragment, producing broad, irrelevant file lists. This is a concrete implementation failure, not evidence that graph retrieval inherently cannot find code.

| Repository | Hidden questions | Adaptive containment passes |
|---|---|---|
| Apache Airflow | 136 | 128/136 (94.12%) |
| MLflow | 51 | 51/51 (100%) |
| .NET eShop | 28 | 28/28 (100%) |
| Spring Petclinic | 14 | 14/14 (100%) |
| OpenMRS Core | 9 | 9/9 (100%) |
| Synthetic platform | 4 | 4/4 (100%) |

Airflow supplies 56.2% of the test, and several other repository samples are small. These results do not establish equally reliable generalization across projects. The four synthetic questions should remain identifiable separately from real-repository evidence.

## 10. Statistical evidence and the oracle discrepancy

The saved final adaptive-versus-fixed-hybrid latency comparison uses 242 paired questions. It reports a mean difference of −0.445370 seconds, paired-bootstrap 95% interval [−0.806184, −0.195464], Wilcoxon p approximately 4.59 × 10^-9, and Holm-adjusted p approximately 1.38 × 10^-8. The interval estimates the mean difference, not the difference between medians. These tests describe the historical observations; they do not remove timing confounds.

The containment difference between adaptive and fixed hybrid is zero. Adaptive exceeds fixed graph by only 1/242, or 0.413 percentage points; the saved overall Holm-adjusted p-value for that comparison is 1.0. This is not evidence of a reliable accuracy improvement over fixed graph.

Adaptive also exceeds the oracle-labelled baseline by one question. On issue_pr_analysis-030, asking for an eShop issue number, adaptive answers 475 while oracle abstains. Both select graph retrieval. Consequently, the discrepancy cannot be explained solely by routing choice. Different execution/fallback behavior and fragile title parsing require a controlled replay before assigning the exact historical cause.

## 11. Development ablations and scalability

Ablation artifacts exist for the full system and twelve variants. These are development results, distinct from the 242-question final comparison:

| Development variant | Rows | Containment % | Mean time (s) |
|---|---|---|---|
| fixed_1hop | 29 | 100.00 | 0.215 |
| fixed_2hop | 29 | 100.00 | 0.238 |
| fixed_3hop | 29 | 100.00 | 0.241 |
| full_system | 29 | 100.00 | 0.217 |
| fusion_equal_weight | 29 | 100.00 | 0.337 |
| fusion_graph_heavy | 29 | 100.00 | 0.218 |
| fusion_vector_heavy | 29 | 100.00 | 0.288 |
| no_fallback | 29 | 100.00 | 0.222 |
| no_graph | 29 | 10.34 | 7.681 |
| no_routing | 29 | 100.00 | 0.615 |
| no_templates | 29 | 86.21 | 10.084 |
| no_validation | 29 | 100.00 | 0.214 |
| no_vector | 29 | 100.00 | 0.190 |

The variants remove components, fix traversal depths, or change fusion weights. They are useful exploratory diagnostics, but current ablation semantics are not consistently single-factor changes: disabling routing also affects strict validation, and disabling templates still allows the classifier to consult the registry. Their scores cannot cleanly attribute improvements to individual mechanisms. Small development coverage further limits conclusions.

The saved scalability study uses size parameters of 1,000 and 5,000. These count generated file nodes; total generated nodes are 1,056 and 5,276 after adding commits, developers, and a repository. Reported median one-hop query times are approximately 0.244 and 0.175 seconds, and three-hop times are 0.265 and 0.242 seconds. Lower time at the larger size is an observation from a limited workload, not proof that increasing graph size improves performance.

The vector scalability component uses random-vector index/search measurements, not the full text embedding and answering pipeline. Both graph sizes are below the reported 37,780-node experiment graph. The available measurements therefore do not substantiate large-scale end-to-end adaptive-system scalability.

## 12. What remains unproven

The strongest supported conclusion is that registered graph queries and direct graph answers work well on the existing graph-derived benchmark. Adaptive and fixed hybrid have the same high containment score, and adaptive has lower recorded latency than fixed hybrid in this run.

Several broader conclusions remain unproven: independently judged semantic accuracy; superiority of routing alone; reduction in human-verified hallucinations; robustness to genuinely new question forms; cross-model generalization; and end-to-end scalability beyond the current workload.

The human annotation sheet contains 1,936 rows but no completed labels, and no independent annotator sheets were found in the audit. Adaptive's saved hallucination_rate of approximately 9.53% is a lexical proxy and must not be described as a human-established hallucination rate. Similarly, the recorded 100% routing score does not establish an optimal router, because the evaluator accepts multiple routes for some categories and does not compare counterfactual route outcomes.

The IDE's preview vector file is separate: the audit records 153 rows, including two errors. It is an incomplete run and is excluded from every final table here. Top-level results/statistical_tests.csv also uses a different population in a key comparison; this document uses the final_evaluation_metrics version only.

## 13. Next stage of the experiment

The existing revision plan proposes a new confirmatory study. Its priorities are independently authored, source-verified questions; balanced development and validation coverage; stricter typed answer scoring; tuned semantic and lexical baselines; a shared executor for forced graph/vector/hybrid routes; isolation of the deterministic-answer shortcut; repeated balanced timing with per-stage logs; and completed blinded human annotation.

Unanswerable cases, additional model families, and larger realistic graph/vector workloads are needed before retaining corresponding robustness claims. Exact model, code, prompt, dataset, index, and configuration identities should be recorded per run. Because the old test and its failures have now been inspected, improvements informed by this audit need a fresh or prospectively reserved final test.

These are proposed next steps, not completed results. The present experiment is best reported as a working repository-QA prototype with strong results on a controlled template-based diagnostic and clearly identified requirements for broader validation.

## 14. Evidence and reproducibility guide

All paths below are relative to the project root. Tables in this summary are generated from saved CSVs, and the builder verifies that each final system has exactly the 242 hidden-test IDs.

- README.md: intended experiment sequence, research questions, systems, and split explanation.
- config/experiment.yaml: current generation, retrieval, routing, and fusion configuration.
- data/metadata/summary.json: repository snapshots and mined/processed counts.
- results/graph_validation_report.json: recorded graph counts and structural checks.
- data/benchmark/splits/: benchmark populations, manifest, questions, and retrospective reference key.
- results/final_evaluation/: the eight coherent final raw result files.
- results/final_evaluation_metrics/summary_metrics.csv: overall saved scores and mean latency.
- results/final_evaluation_metrics/report_tables/category_breakdown.csv: category results.
- results/final_evaluation_metrics/statistical_tests.csv: paired final statistical outputs.
- results/ablations/*/evaluation/summary_metrics.csv: development ablation summaries.
- results/scalability.csv: saved component scalability measurements.
- journal_revision/audit_snapshot.txt and GraphRAG_Experiment_Revision_Plan.md: implementation findings, generation modes, per-repository diagnostics, limitations, and proposed revisions.

Prepared from the available project snapshot on 3 October 2026. Historical scores are preserved under their original definitions; proposed changes are not presented as completed work.

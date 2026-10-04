# GraphRAG experiment revision plan for journal submission

Prepared 3 October 2026 | Project-specific review and implementation specification

## 1. Decision and scope

The experiment needs a redesigned evaluation, several code corrections, and new measurements before its strongest journal claims are defensible. The existing pipeline is reusable: repository mining, a Neo4j graph, a FAISS index, system runners, and reporting utilities already exist. The main problems are benchmark independence, measurement validity, fair comparisons, and incomplete provenance—not simply a need for more questions or higher scores.

The appropriate target is an auditable, reproducible experiment with explicit limitations. No empirical experiment can be guaranteed “error free,” and these changes cannot guarantee journal acceptance or that the adaptive system will win. A valid negative or mixed result is preferable to an unsupported positive claim.

This document responds to all 14 issues in `GraphRAG_Paper_Review.docx` and adds problems found by inspecting the supplied project. Reviewer statements are treated as claims to investigate, not instructions to execute. The paper manuscript itself was not supplied, so statements about what appears in the manuscript cannot be independently verified. Code and saved artifacts were inspected locally; no paid inference, graph rebuild, experiment rerun, or human annotation was performed. The old answer key was inspected for this retrospective audit: the old test must not serve as a fresh blind test for changes informed by this review.

Evidence labels used below:

- **Verified:** visible in current source or saved artifacts, or reproduced with an offline check.
- **Unresolved:** historical execution details or causal explanations not established by available logs.
- **Proposed:** a change or new protocol; not an already completed experiment.

Deliverables from this review are this plan, its Word version, and `audit_snapshot.py` / `audit_snapshot.txt`. The experiment source and existing results have not been modified. Paths below are relative to the project root unless an external source is explicitly linked.

## 2. What this project actually measures

The pipeline mines five real repositories—Spring Petclinic, OpenMRS, eShop, Airflow, and MLflow—and also includes a synthetic repository. It preprocesses files and development artifacts, builds a property graph, and indexes text chunks with SentenceTransformers and FAISS. Benchmark questions and answers are generated through predefined Cypher templates. Eight named systems answer those questions, after which offline scripts calculate answer, retrieval, graph, and latency metrics.

The proposed adaptive system uses a rule-based router. Template matches receive confidence 0.95; other signals receive discrete values of 0.75, 0.65, 0.55, or 0.30. The high threshold is 0.85 and the medium threshold is 0.60. It attempts registered graph queries, can fall back to LLM-generated Cypher and vector retrieval, validates evidence, and either returns graph answers directly or calls an LLM.

Two distinct contributions are currently combined: selecting evidence sources and avoiding answer-generation calls through deterministic graph answers. Both may be useful, but a study must separate them to attribute an improvement to routing.

The name GraphRAG should be defined as repository property-graph retrieval in this paper. Do not imply that these systems implement Microsoft's community-summary GraphRAG method; that work addresses a different graph construction and query-focused summarization design. [Source: original GraphRAG paper](https://arxiv.org/abs/2404.16130).

### 2.1 Verified snapshot

| Item | Observed in this workspace | Implication |
|---|---|---|
| Generated benchmark | 300 questions; dev 29, validation 29, hidden test 242 | Do not mix these populations in performance tables. |
| Final raw results | Eight systems, each with exactly the 242 hidden IDs, no missing or extra IDs | `results/final_evaluation/` is the coherent historical run set inspected here. |
| Final metrics | 1,936 rows = 8 × 242 | These metrics still use the problematic definitions described below. |
| Adaptive generation mode | 242/242 answers marked `deterministic_graph` | This run does not establish LLM answer-generation performance. It does not prove zero LLM calls: fallback Cypher generation may still call an LLM. |
| Current registry coverage | All 242 hidden questions match a registered query | The current “template holdout” is not an unseen-template implementation test. Historical freeze order is unresolved. |
| Adaptive old accuracy | 234/242 = 96.6942% | This is expected-entity containment, not validated semantic correctness. |
| Adaptive old Entity F1 | 0.513546 | A different prediction extractor is used; the mismatch needs diagnosis. |
| Oracle old accuracy | 233/242 = 96.2810% | The entire gap is one question, `issue_pr_analysis-030`. |
| Graph node report | 37,780 nodes across six labels | Includes real and synthetic material; graph quality still needs source-level checks. |
| Saved scalability results | Size parameters 1,000 and 5,000 | Insufficient for claims at or above the real graph size. |
| Human annotation | Final sheet has 1,936 rows and no completed labels; no `annotator*.csv` found under results | Annotation infrastructure exists, completed human validation is not established. |
| Unanswerable probes | No matching probe artifact under `data/benchmark/` | Do not claim that approximately 20 probes were evaluated. |
| IDE preview vector file | 153 saved rows, including two error rows | It is partial; do not merge it into the 242-row final run. Its directory name alone does not establish model identity. |
| Model provenance | One global manifest names `gemini-3.1-flash-lite-preview`; per-row model identifiers are absent | The global file cannot prove which model produced every historical result. |

### 2.2 Existing test composition

| Category | Hidden questions |
|---|---:|
| Structure | 40 |
| Code retrieval | 40 |
| Dependency analysis | 35 |
| Documentation lookup | 31 |
| Issue/PR analysis | 32 |
| Developer activity | 20 |
| Multi-hop | 44 |
| Total | 242 |

Neither the current dev nor validation split contains any structure or code-retrieval questions. Each has only two documentation questions. Therefore, the current 29/29 split is inadequate for balanced baseline tuning and router development.

| Repository | Hidden questions | Adaptive historical containment score |
|---|---:|---:|
| apache/airflow | 136 | 128/136 = 94.12% |
| mlflow/mlflow | 51 | 51/51 = 100% |
| dotnet/eShop | 28 | 28/28 = 100% |
| spring-projects/spring-petclinic | 14 | 14/14 = 100% |
| openmrs/openmrs-core | 9 | 9/9 = 100% |
| synthetic-org/platform | 4 | 4/4 = 100% |

These are retrospective diagnostics calculated from saved metrics, not new independently validated performance results. Airflow supplies 56.2% of the hidden questions; pooled accuracy is therefore heavily influenced by it. Synthetic rows must be shown separately from real-repository evaluation.

## 3. Reviewer response and change matrix

| Reviewer issue | Audit finding | Required response | Priority |
|---|---|---|---|
| 1. Self-generated questions | Confirmed template coupling; current registry covers every hidden question | Independent human-authored test; source-verified gold; fresh freeze | P0 |
| 2. Oracle below adaptive | Confirmed one-question gap, with the same selected route | Separate route policy from executor; rename category-label baseline; empirical route oracle | P0 |
| 3. Accuracy/F1 mismatch | Confirmed incompatible scoring mechanisms | Typed gold, common extraction, stricter correctness, evaluator validation | P0 |
| 4. Mixed question sets | Final folder uses 242 consistently; root statistics contain a different population | Run manifests, exact ID gates, regenerated manuscript tables | P0 |
| 5. Unbelievable latency | Wall time contains client pacing/retries; stage logs absent | New timing instrumentation and repeated, interleaved runs | P0 |
| 6. No latency test | Test exists in saved final metrics; manuscript coverage unknown | Report correct test and estimand; repeat on valid new measurements | P0 |
| 7. Weak/unfair baselines | Hard-coded vector k, post-filtering risk, custom framework-named pipelines | Validation-only tuning, corpus parity, accurate baseline names | P0 |
| 8. Router not isolated | Metric accepts any route in two categories; threshold sweep currently has no route effect | Forced-route controls, route utility/regret, functional ablations | P0 |
| 9. Self-graded faithfulness | LLM self-grading not found; lexical proxy found instead | Two independent humans, evidence packets, agreement, optional calibrated judge | P0 |
| 10. One model | Gemini-bound measured systems; no verified cross-family run | Provider-neutral client and second-family controlled experiments | P1 |
| 11. Small scalability study | Confirmed; “nodes” actually counts generated files | Larger graph and index workloads, actual counts, real/hybrid measurements | P1 |
| 12. No repository results | Existing report generator lacks repository table | Per-repository counts/CIs, real-only macro and pooled results | P1 |
| 13. Unanswerables unanalyzed | Probe artifact absent; answerability merge risk also found | Dedicated source-verified negative suite and evaluator repair | P1 |
| 14. No failures | Heuristic failure rates exist; narrative cases can be recovered | Trace-backed cases, full failure taxonomy, evaluator failures separated | P1 |

P0 means complete before a new confirmatory run. P1 means required before retaining the corresponding journal claim; it is not permission to omit an issue silently.

## 4. Problem 1: independent questions and valid ground truth

**Verified evidence.** `generate_benchmark.py` generates template questions and executes Cypher for gold. `query_registry.py` recognizes the same kinds of questions. An offline registry check matched 242/242 hidden questions. The split file reserves templates at the data level, but their implementations remain available in the current registry. The current code cannot substantiate a claim that those query forms were unknown to the system.

Using a graph to derive gold is not automatically invalid: retrieval systems must access facts needed to answer. The problem is evaluating almost exclusively the forms and graph representations the method was designed to execute, without independently validating either question naturalness or graph correctness.

**Required design.** Preserve the old 300-question benchmark as a historical controlled diagnostic. Create a new independent benchmark as the primary evidence for developer assistance. Recruit developers or students who can understand the repositories; record experience and repository familiarity. Authors should see frozen repository source, documentation, and issue/commit archives, but not the query registry, generated questions, router rules, or system answers. Give task categories and realistic scenarios without prescribing template wording. Record authorship and any assistance used.

Have independent validators verify answers against frozen source artifacts, not merely execute the experiment graph. For each question, record repository snapshot, task intent, answer type, required facts, canonical entities, acceptable alternatives, exact supporting spans, and answerability within the declared corpus. Resolve ambiguity and incomplete questions before system evaluation. Retain valid difficult questions rather than rejecting them because the proposed method fails.

**Proposed planning target, not a power guarantee:** 100 development questions, 100 validation questions, and 300 independently authored answerable final questions. Include structural, semantic explanation, code search, change-history, and multi-artifact tasks. Add a separate final negative suite of 100 questions, divided between verified absent targets and insufficient-corpus-evidence cases. Include negative examples in development too. Adjust these targets using pilot variance, annotation capacity, and a prespecified meaningful effect size; record any adjustment before final evaluation.

Group related questions by author/task family/source artifact before splitting, so paraphrases or nearly identical facts do not cross development/test boundaries. Ensure each task class appears in development and validation on development repositories. For strict repository transfer, collect all test questions for one or more genuinely new repositories only after policy freezing. A repository already analyzed in this review is not a fresh unseen development target.

An indexed holdout repository is legitimate: RAG needs its corpus at inference. The claim is transfer to a repository not used to tune the method, not answering without access to its data. Public-model pretraining contamination remains uncertain; do not claim Airflow was unseen by the language model.

**Source changes.** Extend `split_benchmark.py` with grouped splits and coverage assertions. Add proposed modules `src/benchmark_gen/import_human_benchmark.py` and `validate_independent_gold.py`. Store human questions separately from synthetic/template questions. Require benchmark-version and snapshot hashes. Keep the independent final answers inaccessible to the experiment runner.

**Completion evidence.** Authoring protocol; deduplication report; independent gold review; per-split counts; held-out author/task/repository manifest; frozen benchmark hash; no final-set-guided tuning. If outcomes cause subsequent redesign, label that analysis exploratory and obtain a new confirmatory set or prospectively reserved wave.

## 5. Problem 2: repair what “oracle” means

**Verified evidence.** The current oracle loads `expected_retrieval_route` by question text, sometimes widens it using the template registry, and uses its own execution logic. Category-based labels are not optimal-route labels. Hybrid retrieves both pools, but after ranking, truncation, or synthesis, adding evidence does not guarantee a better answer.

In the saved results, `issue_pr_analysis-030` asks for the issue number for “Can't find API Getway project” in eShop. Adaptive answers `475`; oracle abstains. Both record `graph` as the selected route. This gap cannot be attributed solely to choosing graph versus vector. The title parser is fragile around apostrophes, and adaptive has additional fallback behavior; historical logs/code provenance are insufficient to assign the exact cause without a controlled replay.

**Required changes.** Retain the existing concept only as a clearly named **category-label routing baseline**. Remove missing-label fallback from a strict oracle experiment: a missing route label should fail setup. Use question IDs rather than exact-text lookup, and provide a private ID-to-route sidecar instead of loading a full answer key into ordinary runners.

Create a shared route executor with identical graph retrieval, vector retrieval, validation, fusion, answer mode, and resource limits. For each evaluation question and fixed model, execute graph, vector, and hybrid under this same executor. The router is the only intervention in the routing study.

Define the empirical quality oracle after execution as the maximum prespecified answer-quality score among these forced-route outputs. Break quality ties using a frozen cost rule if reporting a quality-constrained cost oracle. Record the actual sampled outputs and reuse them to evaluate route choices: separately regenerated oracle answers can vary and are not a mathematical upper bound on another sampled run. If adaptive fallback uses extra actions, include those policies in the oracle action set or explicitly limit the ceiling claim to the three forced actions.

The oracle is a diagnostic upper bound over evaluated actions, not a deployable competitor. Its apparent latency is not an achievable online latency if selecting it required evaluating all actions.

**Completion evidence.** Shared executor contract; route coverage 100%; question-level comparison table; `oracle_quality >= selected_action_quality` for the same candidate outcomes; replay of the saved one-question disagreement; clear disclosure of offline gold use.

## 6. Problem 3: replace misleading accuracy and align Entity F1

**Verified evidence.** `metrics.py::coverage` assigns accuracy 1 when all expected entities occur in normalized answer text. It does not reject additional wrong entities or contradictions. `contained` first accepts unrestricted substrings. Thus an expected number can match part of a different number. Entity F1 uses `predicted_entities` if supplied, otherwise regex extraction for paths, issues, commits, and symbols. Ordinary issue titles, numeric answers, developer identities, and structured values can be handled inconsistently.

These two numbers can legitimately differ mathematically. The task is to identify whether the difference comes from extra entities, extraction errors, or wrong gold—not force them to agree. An answer containing the gold entity plus many false candidates can pass current accuracy and deserve low precision.

**Required metric contract.**

| Answer type | Primary correctness rule | Supporting measures |
|---|---|---|
| One entity/value | Exact typed match after declared normalization; no contradictory additional answer | Entity precision/recall/F1 |
| Complete unordered set | Predicted set equals validated gold set | Macro per-question F1 and micro entity F1 |
| Ranked or top-k list | Correct requested membership plus declared ordering/tie policy | Rank metric where meaningful |
| Explanation | Human-validated required facts, factual correctness, and support; explicit rule for full correctness | Fact coverage, unsupported/contradicted claim rates |
| Negative/insufficient evidence | Appropriate abstention without invented assertions | Answerability confusion matrix |

Use one common evaluator-owned parser or schema for all systems. Typed canonical IDs should include repository and entity type. Normalize only what the task permits: do not lowercase case-sensitive paths or conflate issue numbers from different repositories. Serialize structured predictions for all systems consistently, but independently verify that those fields agree with the displayed answer. Do not rely on unverified system self-reported entities.

Report strict full correctness, entity F1, required-fact coverage, and answer coverage separately. Preserve the old score under the explicit label `expected_entity_containment` for historical comparison; do not overwrite it with a newly defined “accuracy.”

Audit a stratified disagreement set where containment=1 but F1 is low. Classify scorer extraction failure, extra false entities, incomplete answer, contradiction, and annotation error. Count each category and preserve examples.

**Evaluator acceptance cases.** Correct entity only; gold plus a wrong entity; negated gold statement; numeric substring collision; same basename in different directories; same issue number in different repositories; short/full commit aliases; apostrophes and quoted code; empty predictions; answerable abstention; correct negative abstention. Include expected outcomes written before code changes. Validate the evaluator against independently labeled answers.

**Completion evidence.** Metric specification with equations and normalization policy; evaluator tests; human agreement with automated scoring on supported answer types; all historical systems rescored together; new final metrics versioned separately.

## 7. Problem 4: one population per table and immutable run provenance

**Verified evidence.** The inspected final raw files all contain the exact 242 hidden IDs. The final category table is consistent with the 242 category counts listed earlier; the alleged 300/242 mixture is not reproduced in this folder. However, top-level `results/statistical_tests.csv` contains an adaptive/fixed-hybrid comparison with n=244 and very different means. `metrics.py` recursively scans CSV files beneath its input directory, so a broad input such as `results/` can collect pilots, ablations, previews, and finals. The root folder is unsafe as an unspecified manuscript source.

**Required changes.** Select raw files through an explicit run manifest, not directory recursion. Use a new run directory for every benchmark/model/code/config combination. Never silently combine preview and final files, even if question IDs match. Record `experiment_id`, `benchmark_id`, `split`, `question_id`, `system`, `model_id`, `repeat_id`, `attempt_id`, snapshot hash, code hash, prompt hash, index hash, and configuration hash. A resumption key must include the run identity, not only question ID/repeat number.

Before scoring, assert unique keys, identical intended question sets, valid reference joins, and no unapproved source files. Persist failed attempts rather than deleting them on resume; the current runner discards failed rows before retrying. Keep an append-only attempt ledger and derive the final selected attempt using a policy specified before the run.

Preserve repository, benchmark, model, repeat, and timing metadata in `evaluate_row`; currently key fields such as `source_repo` and `run_id` do not survive into its returned metrics. Make all tables consume the same validated metrics artifact. Export counts beside category/repository scores and compute denominators from records. Display missing metrics as N/A, never as zero.

**Completion evidence.** An independent reader can trace every table cell to manifest-selected question IDs and raw outputs. Category/repository denominators sum to the declared population. Repeats do not masquerade as additional independent questions. Old and new results remain clearly labeled.

## 8. Problems 5 and 6: latency, repeated measurements, and statistical claims

### 8.1 What the saved numbers establish

`BaseSystem.run` times the whole `answer()` call using `perf_counter`. `GeminiClient.generate` can sleep for client pacing and run retries. These are valid contributors to experienced wall time, but they are not isolated retrieval or model-service latency. A 175-second response is possible; the existing logs do not prove that retries caused each long call.

| Saved statistic | Adaptive | Fixed hybrid | Meaning |
|---|---:|---:|---|
| Median latency | 0.288776 s | 0.335199 s | Difference between marginal medians ≈ −0.046423 s |
| Mean latency | 1.069926 s | 1.515296 s | Mean paired difference ≈ −0.445370 s for identical IDs |

The final statistics file already contains n=242, Wilcoxon p=4.59×10^-9, Holm-adjusted p=1.38×10^-8, and a paired-bootstrap 95% interval for the **mean difference** of [−0.806184, −0.195464] seconds. These are existing saved outputs, not fresh validated timing evidence. The interval does not estimate the difference between marginal medians. The historical test cannot correct uncontrolled execution order, retry exposure, or different generation modes.

Plain LLM has median 175.316631 s and mean 95.080201 s in this folder; vector RAG has median 176.219133 s and mean 177.585978 s. Do not mix medians from the manuscript table with means from the summary file.

### 8.2 Required timing protocol

Instrument monotonic timings and events for routing, embedding, graph query, vector search, fusion, evidence validation, Cypher generation, final generation, client pacing, retry backoff, and total wall time. Record every provider call, attempt count, error class, cache hit, input/output tokens, actual model, and response identifier where available. Count calls used for fallback query generation even when the final answer is deterministic.

Define two endpoints before execution:

1. **Controlled steady-state latency:** warmed services, cache policy fixed, adequate quota, all accepted measurements satisfying predefined no-retry/no-client-wait conditions. Log violations and counts. If a violation invalidates a comparison block, repeat the whole block under the rule, retaining the original attempts.
2. **Operational wall latency:** all queueing, client waits, retry backoff, failures, and timeouts included. Report service reliability and time-to-terminal-outcome under a common timeout policy.

Do not remove slow observations merely because they are slow. Never present success-only latency without its exclusions and failure rates. Separate cold-start initialization from steady-state query timing, since some resources initialize before the runner's timer and some load lazily inside it.

Use randomized or balanced system order within question/repeat blocks. Fix quota tier, concurrency, region, hardware, database/index state, and warmup procedure. Use at least three repeats initially, with five planned if feasible; use pilot variability and precision targets to finalize the repeat count. These are design choices, not a guarantee of adequate power. Repeat blocks should span enough execution periods to reveal temporal drift.

Report mean/SD, median/IQR, p95, failure/timeout rate, and paired confidence intervals. For routing comparisons, use identical answer-generation policies. Separately report the deployment benefit of deterministic shortcuts.

### 8.3 Required analysis

Preregister adaptive versus fixed hybrid as the primary routing comparison. Specify the latency endpoint and a smallest practically meaningful benefit before inspecting final results. Prespecify an acceptable answer-quality loss margin if claiming “same quality with lower latency.” A nonsignificant quality difference does not establish equivalence or noninferiority.

For each question, aggregate repeated latency under the declared rule, then compare paired question-level differences. Use Wilcoxon signed-rank where the paired-difference assumptions are reasonable; it is not a generic test of arbitrary skewed latency distributions. Record the zero/tie convention and library version. A paired bootstrap interval estimates a separately declared quantity such as mean difference, median paired difference, or difference of medians. Choose the estimator explicitly. [Source: SciPy Wilcoxon documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.wilcoxon.html).

Account for shared task families and repositories in sensitivity analyses. Do not treat three repeats of one question as three independent questions. A cluster bootstrap over task families, with repeats retained inside questions, is useful when enough independent clusters exist. With only five real repositories, repository-wide population claims remain imprecise even with hundreds of questions. Report per-repository effects and uncertainty rather than hiding this limitation.

Use a paired binary test such as exact McNemar for strict correctness, paired bootstrap intervals for quality differences, and prespecified multiplicity correction for the family of confirmatory comparisons. Existing Holm correction is within metric/subgroup, not automatically across every claim in a paper. Label exploratory subgroup results accordingly. Publish inconclusive or negative results without retuning on the final set.

**Completion evidence.** Raw attempt timings; exclusion ledger; repeated balanced schedule; verified metadata; quality and latency intervals; reproducible statistical script; claims matched to the actual estimand and run population.

## 9. Problem 7: credible baselines and a fair comparison

**Verified weaknesses.** Vector RAG hard-codes `k=10`, so editing `vector.top_k` alone will not tune it. Chunking uses characters (1,200 with 180 overlap), not tokens. Search retrieves at most 5k global candidates before applying a repository filter, which can return fewer than k repository results even when more relevant candidates exist. Gold-evidence matching is permissive and does not yet support a reliable diagnosis of retrieval quality.

The named LangChain and LlamaIndex modules are custom direct NL-to-Cypher pipelines. They do not import those frameworks, and those frameworks are not listed in the project requirements. Rename them to describe their actual mechanisms, or implement and pin genuine framework baselines. Do not claim superiority over entire frameworks from these two prompt variants.

**Required baseline matrix.**

| Baseline/control | Role in the revised experiment |
|---|---|
| Plain LLM without retrieval | Context for repository specificity; disclose its cautious prompt and abstention behavior |
| Tuned dense vector RAG | Main semantic retrieval baseline |
| Lexical code/text search, optionally lexical+dense fusion | Strong practical control for exact identifiers and code snippets |
| Registered-query graph-only | Measures the benefit of direct graph/template answering |
| Controlled NL-to-Cypher | Measures graph retrieval without registered templates |
| Fixed hybrid using shared executor | Primary routing comparator |
| Adaptive using shared executor | Proposed route-selection policy |
| Category-label policy and empirical oracle | Diagnostic policies, with oracle excluded from deployable rankings |

Use the same frozen corpus, repository access, source snapshots, generation model, final-answer settings, and declared evidence-token budget within each controlled comparison. Graph relation facts should be traceable to raw artifacts available to the vector/lexical baselines. Where the graph gives structured information not otherwise indexed, either provide equivalent serialized facts to an additional vector baseline or explicitly identify the representation difference as part of the experiment.

Create an adequate development set before tuning. Suggested search space: token-aware chunk sizes 256/512/1,024, overlap 10–20%, k=5/10/20/40, repository prefiltering, and a bounded choice of embedding/reranking strategies. This is a proposal, not a claim that these values are optimal. Give competing methods comparable tuning effort and token/cost limits. Select on validation quality and cost under a frozen rule, then lock the selected configuration.

Ensure chunks fit the selected embedding model's token limit; character count alone does not ensure this. SentenceTransformers exposes maximum sequence length and model-specific encoding options, so record the actual values used. [Source: SentenceTransformers documentation](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html).

Instrument recall before generation: Did the correct artifact exist in the index? Was it retrieved? Did chunk truncation remove the needed span? Did the generator abstain despite sufficient evidence? This separates index, retrieval, and synthesis failures. Validate repository prefiltering with known targets and fewer-than-k cases.

**Completion evidence.** Search log of all validation candidates; chosen configuration; corpus/index coverage audit; exact versions; comparable context budgets; corrected baseline names; no target “minimum baseline accuracy” imposed after seeing results. A low score may remain valid after a fair setup.

## 10. Problem 8: evaluate routing and ablations as actual interventions

**Verified metric issue.** `metrics.py` treats graph, vector, and hybrid as acceptable for every code-retrieval and documentation question. A 100% routing score under this rule is not evidence of optimal decisions. Gold routes come from category labels rather than observed route quality or cost.

**Verified threshold issue.** A template hit has confidence 0.95. All 242 current hidden questions match templates. Moreover, non-template signals whose bands cross 0.70/0.80/0.85/0.90 already prefer hybrid. Thus the requested high-threshold sweep has no effective retrieval-plan change under the current classifier; with medium threshold fixed, it also does not change strict validation. Do not manufacture a sensitivity curve from an intervention that changes no decisions.

**Required outputs.** Record preferred route, confidence/score, selected initial route, actual sources used after fallback, fallbacks, quality, latency, tokens, and LLM calls. Evaluate:

- Route confusion matrix against independently justified reference actions, with ties allowed only by a declared utility rule.
- Quality regret: best available forced-route quality minus selected-route quality.
- Cost regret among actions meeting the predefined quality constraint.
- Unnecessary hybrid rate, missed-evidence rate, fallback rescue rate, and route distribution by question type/repository.
- Confidence calibration only if scores are interpreted as probabilities; otherwise call them heuristic scores.

Implement a policy that can genuinely vary with thresholds, or explicitly report the current sweep as a null intervention and narrow the claims. Tune any redesigned policy only on fresh development data. Run the requested 0.70/0.80/0.85/0.90 settings and record route-change counts; add threshold values near actual score boundaries only with a development-stage rationale.

**Causal ablations.** Use one executor and change one mechanism at a time: learned/rule router versus always graph, always vector, always hybrid; template use on/off; fallback on/off; validation on/off; deterministic answer shortcut on/off. Keep other policies fixed. In the current code, `--no-routing` also disables strict validation, while `--no-templates` still allows `classify()` to consult the registry. Those are not clean single-factor removals.

Fixed-hop variants currently pass a hint only to LLM-generated Cypher; registered templates are unaffected. The router's inferred hops are not passed as the default hop hint. Consequently, existing fixed-hop flags do not establish adaptive graph traversal. Either implement an executable traversal-depth policy with checked graph paths, or remove that novelty claim and describe the flags accurately as LLM-Cypher prompt hints. Fusion weights change score terms (retrieval, lexical, graph bonus), not direct graph-versus-vector mixing weights; rename graph-heavy/vector-heavy variants accordingly.

Use trace assertions to prove that every ablation changed the intended mechanism. Run development ablations for selection and a frozen, prespecified subset on the new test for confirmation.

**Completion evidence.** Counterfactual forced-route dataset; exact executor parity; route-change counts; regret/quality/cost tables; validated ablation traces; real routing failures, if observed, explained without inventing examples.

## 11. Problem 9: valid human faithfulness evaluation

**Verified correction to the review.** The inspected evaluator does not ask Gemini to judge its own answers. Instead, it tests lexical overlap against required facts, gold identifiers, and expected entities. This is not semantic entailment, and it is not necessarily faithfulness to the evidence actually supplied to the answering system. The current very high plain-LLM “hallucination rate” coexists with frequent abstention, illustrating why non-answer statements must not be treated automatically as invented factual claims.

Retain this old metric only as a clearly labeled lexical support proxy. Distinguish answer correctness against source truth from faithfulness to retrieved evidence. An answer can be factually correct but unsupported by its provided context, or supported by an erroneous retrieved artifact. Evaluate these separately. RAGAs likewise treats RAG evaluation as multiple dimensions; using any automated evaluator still requires validation for this task. [Source: RAGAs paper](https://aclanthology.org/2024.eacl-demo.16/).

**Human protocol.** Select a stratified random sample across systems, models, repositories, question types, generation modes, and answerability. Keep the same sampled questions across systems where comparison matters. The review's example of 100 answers is a minimum audit, not enough by itself to support precise claims across eight systems. A practical target is 50 questions × six core deployable systems = 300 answers per model, judged independently by two people; adjust through an explicit precision/workload plan. If strata are oversampled, use sampling weights for population summaries.

Give annotators question text, the frozen source evidence needed for correctness, and the actual retrieved context needed for faithfulness. Hide system/model names and evaluation scores. The current annotation builder lacks retrieved-context packets; extend it. Store stable answer IDs including model and repeat. Provide a codebook separating supported, unsupported, contradicted, incomplete, irrelevant, and appropriate abstention. Specify whether labels are per claim, mutually exclusive classes, or independent binary fields; do not mix these conventions.

Calibrate on a separate pilot set, then lock the codebook. Annotators work independently before adjudication. Report raw agreement, label prevalence/confusion, and Cohen's kappa for two raters or an appropriate Krippendorff alpha formulation. Calculate agreement on original labels, not adjudicated labels. Include uncertainty and disagreement reasons. Poor agreement requires revising instructions and reassessing the sample, not quietly discarding difficult cases.

An independent-family LLM judge can be supplementary if calibrated against humans. Pin its model/prompt, blind candidate identities, and report judge errors; switching judge model alone does not guarantee independence or correctness.

**Completion evidence.** Sampling manifest; evidence packets; codebook; two untouched annotation sheets; agreement results; adjudicated labels; separate correctness and faithfulness tables. Until these exist, do not claim human-validated hallucination reduction.

## 12. Problem 10: a genuine second-model evaluation

The measured systems instantiate `GeminiClient` directly. Ollama's use to phrase synthetic text or paraphrase questions does not count as evaluating a second answer model. The global environment manifest is not bound to each result directory, and the preview folder lacks row-level model provenance.

Add a provider-neutral generation interface with text, model identifier, token usage, finish reason, cache status, call/attempt records, and timing. Implement the existing Gemini backend plus a separately selected non-Gemini model family. Choose an exact model/version suitable for available hardware, context length, and licensing at implementation time; this plan does not select a current deployment or promise its cost.

For the second model, repeat at least tuned vector, graph-only, fixed hybrid, and adaptive on the same fresh frozen independent test; include the plain-LLM and NL-to-Cypher controls where claims depend on them. Switch both final-answer and query-generation calls. Freeze shared retrieval settings for the main transfer test; any model-specific retuning must occur on development data and be reported separately with equal budgets.

Report system effects within each model. A local model and a hosted model have different hardware/service conditions, so do not attribute their absolute latency difference solely to model family. Report generation-mode proportions: repeating a fully deterministic workload with a second model adds little evidence of model robustness.

**Completion evidence.** Two model-specific manifests and complete result matrices; exact parameters; within-model quality/latency comparisons; analysis on questions that actually invoke model generation; no blending of preview results.

## 13. Problem 11: scalability beyond the current workload

`generate_and_measure.py` measures graph query workloads and random-vector FAISS search. It builds `size` file nodes plus commits, developers, and one repository, but reports `nodes=size`. Actual node count is `size + max(1,size//20) + max(1,size//200) + 1`. Thus the existing 1,000/5,000 parameters correspond to 1,056/5,276 nodes, not 1,000/5,000 total nodes. It also maintains roughly constant commits per developer, so some local-query work may stay almost constant as global size grows. That is a workload property, not proof of general scalability.

Run a dedicated local experiment database at actual total-node targets of 10,000, approximately the real 37,780-node scale, 50,000, and 100,000. Larger sizes are optional if feasible. Count nodes/edges after construction, verify expected indexes are online, and record per-label counts, degrees, graph density, selectivity, result cardinality, query plans, database version, hardware, and cache state.

Vary both global graph size and difficult local structures: high-degree developers/files, long histories, broader aggregations, and bounded/unbounded result workloads. Keep representative query families and seeds fixed across scales. State limits explicitly; a `LIMIT 100` query does not establish behavior for complete enumeration.

Report build/index time, disk and peak memory, p50/p95 query latency, IQR, throughput at declared concurrency, failure rates, and answer/retrieval correctness. Use multiple graph instances/seeds and varied query instances, not only five repeats of one query. For vector scalability, separate random-vector index microbenchmarks from real-text chunking, embedding, query encoding, and retrieval. Add end-to-end graph/vector/fixed/adaptive measurements at matched corpus sizes; component microbenchmarks alone do not demonstrate adaptive-system scalability.

**Completion evidence.** Actual-size manifest; raw repetitions; workload definitions; correctness checks; resource measurements; plots with uncertainty. If 100,000 nodes cannot run, report the measured limit and reduce the claim rather than extrapolating.

## 14. Problem 12: per-repository results and the meaning of holdout

Extend `metrics.py` to retain source repository and `report_tables.py` to produce repository breakdowns for every system and model. Show n, category mix, strict correctness, Entity F1, evidence recall, abstention, latency, and confidence intervals. Publish both question-weighted overall results and an unweighted average across real repositories. Separate synthetic results.

The current Airflow score is retrospectively computable (94.12% under old containment), but all its questions match registered forms in the current implementation. Neither that score nor holding out its question IDs proves generalization to unfamiliar query forms. Repository snapshot inclusion in retrieval is expected; exclusion from method development is the relevant condition.

For stronger transfer evidence, use a prospectively held-out repository, preferably more than one diverse repository if resources allow. A leave-one-repository-out study is useful only if each fold's tuning is confined to the other repositories; merely regrouping existing predictions is not retraining-free proof of that protocol. Describe public-pretraining exposure as an unresolved limitation.

**Completion evidence.** Counts/intervals for each repository; real-only pooled and macro scores; transfer protocol; held-out development history; appropriately limited conclusions for small repository samples.

## 15. Problem 13: unanswerability is not the same as graph absence

No saved probe file was found. The README correctly describes approximately 20 as a generator target separate from the 300-question benchmark. Do not report a realized probe count without artifacts.

Generate source-verified questions with nonexistent targets, absent relationships, unsupported premises, insufficient mined evidence, and ambiguous requests requiring clarification. Distinguish **not in this graph**, **not in the declared frozen corpus**, and **verified absent in the repository snapshot**. Mining limits and preprocessing exclusions mean an empty graph result alone cannot prove repository nonexistence. Do not make negative examples trivially detectable from unusual IDs or category formatting.

A further evaluator repair is required: `merge_benchmark` does not include `answerable` in its authoritative gold fields. If both result and gold contain the column, the evaluator can keep the result's value rather than the gold value; missing labels default to True. Make answerability mandatory for the new benchmark and exclusively evaluator-owned. Validate joins and prohibit silent defaults. With empty expected entities, negative correctness must be scored by a dedicated abstention rule rather than ordinary entity containment.

Report correct abstention rate on unanswerables, false-answer rate on unanswerables, unnecessary abstention rate on answerables, answer coverage, and accuracy conditional on answering. Also report overall task success under the predeclared population prevalence. Do not count an API error, empty output, or timeout as a correct abstention. For an insufficient-corpus question, the safe answer is that evidence is insufficient; it need not assert nonexistence.

**Completion evidence.** Private source-verified labels; gold-stripped runner inputs; negative-suite manifest; confusion matrices by system/model/subtype; semantic checking of abstentions; no claimed results from absent probes.

## 16. Problem 14: trace-backed failure examples

The current `failure_analysis.csv` contains heuristic rates. It does not substitute for a documented explanation of actual failures. The following are real saved cases or reproducible local parser diagnostics, not fabricated examples:

| Case | Observation | Supported diagnosis and required fix |
|---|---|---|
| `code_retrieval-001` | A fragment containing nested quotes is parsed as `)}`; adaptive returns a broad file list and scores 0 | `_fragment` selects the last quote-delimited substring; preserve the complete outer snippet and validate evidence against the original text. |
| `code_retrieval-020` | Import statement containing `"src/components/Graph/DownloadButton"` is parsed as `;` | Parameter extraction failure, not demonstrated routing failure; add nested-quote regression cases and constrain matching to the intended span. |
| `code_retrieval-037` | Python f-string fragment is parsed as `)` | Broad matches and result limits can omit the intended answer; fix parsing and expose cardinality/truncation. |
| `code_retrieval-022` | Callback containing `handleScrollTo("top")` is parsed as `),` | Same failure family; use it as a regression case, not a fourth independent failure category. |
| `issue_pr_analysis-030` | Adaptive returns 475; oracle abstains; both select graph | Executor/fallback/run mismatch is supported; exact historical cause requires replay. Do not label it a router error. |

All eight adaptive containment failures in the inspected run are code-retrieval questions with nested quotes; the current parser reduces them to short punctuation fragments. This is an offline reproduction of current parsing behavior. Confirm the link to each historical run using saved parameters/trace and snapshot before asserting a complete historical causal reconstruction.

Revise parsing in `query_registry.py`: bind outer delimiters to the recognized question structure, preserve internal quotes/apostrophes, handle escaped text, and reject ambiguity rather than execute a corrupted parameter. For naturally authored questions use robust extraction, with deterministic validation against original input, rather than relying solely on one wording. Reject or flag unexpectedly broad matches and require source evidence that contains the intended snippet. Do not “fix” the benchmark by deleting inconvenient quotes.

In the new study, select 3–5 representative failures covering observed categories such as retrieval omission, incorrect relation, generation hallucination, false abstention, and routing regret. If a category is absent, say so. Include question ID, original question, gold/support, answer excerpt, initial/actual route, evidence, root-cause confidence, proposed remedy, and whether a replay confirms the cause. Report frequencies separately from illustrative examples. Never adjust the final system using these test cases and continue calling that test untouched.

## 17. Additional defects that must be fixed for valid claims

### 17.1 Retrieval metrics need real evidence identities

`build_gold_evidence` currently creates descriptors such as repository, query parameters, answer values, and relation names. `evidence_match` accepts substrings, basename matches, and token similarity. A matching repository or common basename does not establish retrieval of the fact needed to answer. This can make retrieval precision look high while answer accuracy is very low.

Replace descriptors with canonical source IDs and supporting spans: repository + commit/snapshot + path + line/character range; issue/PR ID + field; graph edge/path IDs linked to originating artifacts. Define gold evidence at artifact or chunk granularity explicitly, accommodate multiple valid supporting evidence sets, and deduplicate repeated chunks from one artifact where appropriate. Score exact IDs/spans using explicit equivalence maps rather than arbitrary fuzzy matching. Assess evidence relevance with independent annotation on a sample.

### 17.2 Path and relation scores currently risk circularity

Adaptive `predicted_relations` and `predicted_path` are populated from template metadata when a graph result exists. This does not show that a predicted entity-level path was reconstructed correctly. Benchmark gold uses corresponding schema descriptions. Return actual node/edge identifiers or evidence-backed relation tuples from query execution and evaluate those against independent gold. Otherwise relabel these measures as schema/template agreement and remove reasoning-success claims based on them.

### 17.3 Deterministic answers bypass evidence budgets

Direct graph answers use graph rows rather than the final fused evidence list. Template queries may return up to 100 rows while final evidence is capped at 16. Retrieval metrics over fused evidence therefore need not describe everything used in the deterministic answer. Record the exact answer-support set for both modes. For a routing-only study, apply common budgets and answer policy; for the full deployed design, disclose shortcut behavior and provide a shortcut-disabled ablation.

### 17.4 Validate what “dependency” and “multi-hop” mean

The graph and templates include commit/file modification relations. A question about files modified by a commit is not necessarily program dependency analysis. If the paper claims code dependency reasoning, add actual import/call/package dependency extraction with independently verified gold, or rename the category to change-history/impact lookup. State whether “hop count” refers to schema edges, executed traversal, or necessary reasoning steps. Do not infer semantic reasoning depth solely by counting relation names.

### 17.5 Source quality and corpus parity

Validate sampled mined facts against source snapshots and archive issue/PR content and timestamps. A repository commit SHA does not freeze later issue metadata. Record extraction limits, exclusions, truncation, missing identities/edges, and synthetic provenance. Synthetic content should be a separate robustness track, not counted silently as real developer evidence. A graph with no orphan nodes is not necessarily complete or semantically correct.

### 17.6 Reproducibility metadata must describe the actual run

Requirements use lower bounds, while the global environment manifest records an editable package path elsewhere and no Git commit. Verify imported module locations and record a source archive hash if no Git repository is available. Save a per-run dependency lock, configuration, model ID/version, hardware, prompts, and dataset/index hashes. Do not infer historical run identity from today's environment or file modification times. If provenance cannot be reconstructed, keep those results as exploratory and rerun.

## 18. Implementation work packages

These are proposed engineering tasks. Suggested new paths do not imply the modules already exist.

| Work package | Existing/new files | Concrete change | Acceptance check |
|---|---|---|---|
| WP1: freeze and provenance | `scripts/record_environment.py`, `src/systems/base.py`; new run-manifest utility | Per-run immutable IDs/hashes; append-only attempts; robust resume keys | Different model/config cannot resume into same run; all attempted calls retained |
| WP2: independent benchmark | `src/benchmark_gen/split_benchmark.py`; new import/validation modules | Human task import, source gold, grouped splits, coverage checks, private labels | No duplicated task groups; complete dev coverage; final leakage audit |
| WP3: parsing and graph validation | `query_registry.py`, `retrieval_core.py` | Robust quoted text; source-level verification; actual path evidence | Nested quotes/apostrophes parsed intact; no punctuation-only broad query |
| WP4: scorer redesign | `src/evaluation/metrics.py` | Typed correctness, evidence IDs, answerability join, metadata preservation | Evaluator challenge cases and human comparison pass |
| WP5: executor and router isolation | adaptive/fixed/oracle systems, `router.py`, new shared executor | Forced routes, identical answer policy, empirical oracle, genuine ablations | Policy is only difference; ablation trace shows intended intervention |
| WP6: baseline tuning | `vector_store.py`, `vector_rag.py`, framework-named systems | Configurable k/token chunks; repository filtering; truthful naming; lexical control | Index coverage and tuning artifacts published |
| WP7: timing/model interface | `src/llm.py`, `src/common.py`, `base.py`, system constructors | Provider interface, stage timing, token/call/cache/retry logs, second backend | Error/retry/cache simulations produce correct ledger and totals |
| WP8: analysis/reporting | `statistics.py`, `report_tables.py`, run scripts | Strict input manifest; paired repeats; repository/answerability/router tables | Same IDs/denominators throughout; tables regenerate without manual edits |
| WP9: human evaluation | `hallucination_annotation.py`, `agreement.py` | Actual evidence packets, blinded stable IDs, independent labels | Agreement computed before adjudication; coverage and sampling documented |
| WP10: scalability | `src/scalability/generate_and_measure.py` | Actual sizes, variable workloads, resource metrics, hybrid end-to-end | Counts verified; workloads correct; raw timings and hardware saved |

Update README claims alongside implementation: shared answer prompt applies to grounded generation, not every possible execution; plain LLM intentionally has a different no-retrieval prompt; template holdout is not automatically implementation holdout; heuristic scores are not calibrated probabilities; current generation modes and real model-call counts must be disclosed. Replace regression expectations that regard vector failure as a desired outcome with mechanism/corpus integrity checks and known-answer smoke tests where evidence is available.

## 19. Revised experimental matrix and practical workload

Use two distinct studies, sharing frozen artifacts:

**Study A: mechanism isolation.** On independent questions, run graph/vector/hybrid/adaptive policies through the common executor, with a shared grounded answer mode. Add the empirical oracle by selecting among the already generated forced-route outputs. This isolates whether route selection improves the quality/cost trade-off.

**Study B: deployed system performance.** Compare full adaptive, full fixed hybrid, tuned vector, graph/template, NL-to-Cypher, and plain LLM under their declared implementations, including deterministic shortcuts. Disclose all differences and add shortcut-disabled/fallback-disabled/validation-disabled controls. This measures the complete design's practical value without assigning every benefit to routing.

| Experiment | Population | Models | Repeats/outputs |
|---|---|---|---|
| Baseline/router tuning | Fresh development and validation only | Primary model; equal-budget secondary tuning if planned | All candidate configs and validation outcomes |
| Main independent benchmark | Proposed 300 answerable questions | Two families | Initially plan 3 repeats, finalize using pilot precision |
| Abstention study | Proposed 100 final negative cases plus answerable controls | Both | Correct/incorrect abstention with full failure denominators |
| Legacy diagnostic | Old 242 plus separately labeled dev/validation if useful | Clearly identified | Historical/rescored comparison, never called a new hidden test |
| Human evaluation | Stratified paired subset | Both where claims apply | Two independent annotations per selected answer |
| Sensitivity/ablations | Dev for selection; frozen subset on new final set | At least primary model | Route-change/trace proof plus quality/cost outcomes |
| Scalability | 10k/real-scale/50k/100k actual nodes | Model fixed for end-to-end | Multiple workloads/seeds and repeated timings |

For budgeting, six deployable systems × 400 final questions × two models × three repeats equals 14,400 answer attempts. This excludes development searches and optional controls; some attempts use no final-answer LLM and some need multiple calls. Estimate cost using pilot-observed calls and tokens per system, not this attempt count alone. The empirical oracle can reuse forced-route outputs. Preselect a representative subset for expensive ablations or annotation if necessary and disclose that scope; never shrink the study after seeing which results are favorable.

## 20. Execution order and stop/go gates

| Phase | Work | Exit gate |
|---|---|---|
| 0. Preserve | Archive old raw results/code/config; designate exploratory sets; freeze audit | Old outputs unchanged; explicit source for every historical number |
| 1. Repair measurement | Scorer, parser, joins, provenance, timing, baseline naming | Offline evaluator and trace tests pass |
| 2. Build new data | Independent authors, source gold, splits, negative cases | Independent review complete; dev coverage adequate; final labels protected |
| 3. Pilot and tune | Baselines, router, provider adapters, costs, repeat precision | Validation-only choices documented; functional ablations; feasible budget |
| 4. Preregister/freeze | Hypotheses, endpoints, margins, exclusions, tests, code/index hashes | Signed/timestamped protocol; independent final set locked |
| 5. Execute | Balanced repeated main runs, second model, negatives, scale | Manifest completeness; no mixed versions; attempt ledger intact |
| 6. Evaluate | Blind human annotation, stats, per-repository/failure analysis | Agreement and scoring audit complete; all tables reproducible |
| 7. Revise paper | Replace unsupported claims, add limitations, reviewer response | Each claim points to a table/figure and validated artifact |

Do not run an expensive final benchmark before Phases 1–4 pass. A practical staffing plan needs an experiment engineer, question authors, and two independent annotators, with an adjudicator available for disagreements. Roles can overlap only where independence is preserved and disclosed; final judges should not be told system identities. Human authoring and annotation are the main external dependencies. Schedule them alongside engineering, not after the final analysis.

If a defect is discovered during final execution, preserve the failed run, document the defect, and decide whether the remedy is outcome-independent. A model, prompt, corpus, scorer, or policy change needs a new version; do not silently resume. If final answers influence design choices, downgrade the affected analysis to exploratory and use a fresh confirmation set.

## 21. Required paper tables, figures, and claims

| Artifact | Minimum content |
|---|---|
| Dataset table | Human/template origin; real/synthetic counts; split, repository, category, answerability; snapshot dates |
| Baseline configuration table | Actual mechanism/framework, model, embeddings, chunks, k, budgets, tuning effort, shortcut/fallback policy |
| Main results | Strict correctness, entity F1, fact coverage, human faithfulness, coverage, failure rate, n and CIs; separate model panels |
| Efficiency table | Controlled and operational latency, p50/p95/mean, calls, tokens, retries, caches, generation modes |
| Primary paired comparison | Quality difference/noninferiority criterion, latency effect and CI, test/effect size, multiplicity convention |
| Router table/plot | Route frequencies, confusion/regret, rescue rate, quality-cost curve, threshold change counts |
| Ablation table | Actual intervention, changed traces, quality/cost; no-op variants labeled |
| Repository table | Per-system/model results, n and CIs; real-only macro and pooled means; synthetic separate |
| Abstention table | Negative subtype, correct abstention, false assertions, unnecessary abstention, errors |
| Scalability plots | Actual nodes/edges, workload definition, uncertainty, memory/build cost and latency |
| Human-evaluation table | Sampling, label prevalence, raw agreement, kappa/alpha, adjudication and judge calibration if used |
| Failure examples | 3–5 trace-backed cases plus aggregate failure counts and evaluator-error counts |

Rewrite the central claim around evidence the new study actually supports. If routing improves latency but slightly lowers accuracy, state that trade-off. If benefits occur primarily on templated structural questions, restrict the claim. If deterministic execution explains most savings, identify that contribution. If performance depends on one model or repository, disclose it. Do not describe containment as semantic correctness, lexical overlap as human faithfulness, or schema metadata as reasoning-path reconstruction.

## 22. Submission acceptance checklist

- [ ] Every reviewer issue has a response tied to a changed method, new result, or explicitly narrowed claim.
- [ ] Independent final questions and source-verified gold exist; the old exposed test is labeled historical/exploratory.
- [ ] Final inputs expose only permitted question/context metadata; answers, route labels, template labels, and evidence annotations stay evaluator-side unless a clearly marked diagnostic requires them.
- [ ] Current public files' `expected_retrieval_route`, `template_name`, and `evidence_entities` have been removed from ordinary final inputs. Current `answer(question)` runners generally use only the question, so their presence is a leakage risk—not proof of historical use.
- [ ] Scorer tests cover false positives, aliases, extra entities, contradictions, and unanswerables; human validation checks scoring validity.
- [ ] Retrieval/path metrics use actual evidence instances, with declared units and support provenance.
- [ ] Baselines have comparable data access and tuning effort; framework names match implementations.
- [ ] Router-only and full-system effects are separated; threshold/ablation changes alter the intended behavior.
- [ ] Per-call timings, model IDs, token/call counts, errors, retries, waits, and caches are logged; no selective deletion of failures.
- [ ] Final runs are complete under immutable manifests; all tables use the intended IDs and metadata.
- [ ] Paired analyses use independent question/task units and clearly defined estimands; uncertainty and practical relevance are reported.
- [ ] Two independent human label sets and agreement results are available; abstention is distinguished from hallucination.
- [ ] A second model family, per-repository results, and a valid negative suite support any corresponding claims.
- [ ] Scalability reaches the claimed scale using actual node counts and meaningful workloads.
- [ ] Failure cases and limitations include unfavorable findings; all headline numbers regenerate from released artifacts.

Passing this checklist means the experiment is substantially more defensible and reproducible. It does not certify the absence of all defects or guarantee acceptance.

## Appendix A. Evidence map and reproducibility of this review

The read-only local audit can be repeated from the project root with `python journal_revision/audit_snapshot.py`. It reads current saved artifacts and exercises the registry parser; it does not contact an LLM or Neo4j. Its output will change if the underlying workspace changes. `audit_snapshot.txt` preserves the output observed during this review.

| Finding | Primary local evidence |
|---|---|
| Counts, split holdouts, label stripping | `data/benchmark/splits/split_manifest.json`; split CSV files; `src/benchmark_gen/split_benchmark.py` |
| Template coupling and gold construction | `src/benchmark_gen/generate_benchmark.py`; `src/systems/query_registry.py` |
| Quoted-snippet defect | `query_registry.py::_fragment`; saved code-retrieval questions; audit parser output |
| Oracle definition and drift risk | `src/systems/oracle_hybrid_rag.py`; `issue_pr_analysis-030` in adaptive/oracle final result files |
| Accuracy/F1/support/route/evidence scoring | `src/evaluation/metrics.py::coverage`, `extract_entities`, `grounding`, `evaluate_row`, `evidence_match` |
| Result ingestion and metadata omissions | `metrics.py::main`, `merge_benchmark`, `evaluate_row`; `src/systems/base.py::run` |
| Latency statistics and disagreement of sources | `results/final_evaluation_metrics/statistical_tests.csv`; `results/statistical_tests.csv`; final summary/main tables |
| Timing and retries | `src/systems/base.py`; `src/llm.py`; `src/common.py`; `config/experiment.yaml` |
| Vector setup and candidate filtering | `src/vector_store.py`; `src/systems/vector_rag.py` |
| Framework-named custom implementations | `src/systems/langchain_graphrag.py`; `llamaindex_graphrag.py`; `requirements.txt` |
| Routing scores and ablation semantics | `src/systems/router.py`; `adaptive_hybrid_graphrag.py`; `scripts/run_ablations.ps1` |
| Annotation status and missing evidence packets | `results/final_evaluation_metrics/hallucination_annotation.csv`; `src/evaluation/hallucination_annotation.py` |
| Scale-count definition and saved sizes | `src/scalability/generate_and_measure.py`; `results/scalability.csv`; `results/graph_validation_report.json` |
| Current model provenance limitation | `results/environment_manifest.json`; raw result schemas; IDE preview file |

External sources were consulted for limited methodological/implementation points, not as evidence about this project's historical execution: [SciPy Wilcoxon](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.wilcoxon.html), [RAGAs](https://aclanthology.org/2024.eacl-demo.16/), [SentenceTransformers](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html), and [GraphRAG](https://arxiv.org/abs/2404.16130). Software documentation is mutable; pin the versions used in the revised experiment. Recommendations, sample targets, and work packages in this document are proposed design decisions rather than claims that a source mandates those exact choices.

## Appendix B. Reviewer response template

For each numbered issue, write the eventual response only after the relevant work is completed:

“We agree that [specific validity concern]. We inspected [artifact/code], which showed [verified diagnosis]. We changed [method or implementation] and evaluated it on [frozen population/model/run]. Table/Figure [reference] reports [observed result with uncertainty]. We have revised the manuscript claim to [supported scope]. The remaining limitation is [limitation].”

For issues where the review's premise differs from the code, respond precisely and respectfully. For example: “The prior faithfulness score was a lexical proxy rather than Gemini self-grading. We agree that it did not establish semantic faithfulness; we replaced the primary claim with independently annotated evidence-based evaluation.” Do not fill in future results, agreement scores, significance, or claims of completed changes until the supporting artifacts exist.

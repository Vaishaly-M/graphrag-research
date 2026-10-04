# Adaptive routing evaluation: frozen 242-question comparison

## Objective and claim

Test whether Adaptive Hybrid GraphRAG improves answer quality and retrieval
efficiency on the **unchanged 242 hidden-test questions and unchanged eight
systems**. Superiority is a hypothesis, never a condition used to choose scores,
questions, baselines, or reported runs. Existing hidden-test results have already
been inspected: this is a revised evaluation on a reused test set, not a newly
unseen confirmatory experiment. Disclose that limitation in the paper.

Keep plain_llm, vector_rag, langchain_graphrag, llamaindex_graphrag,
fixed_graph_rag, fixed_hybrid_rag, oracle_hybrid_rag, and
adaptive_hybrid_graphrag in the main table. The oracle is a gold-label routing
reference, not a deployable competitor or a guaranteed upper bound: its current
implementation can widen a gold route to hybrid, and differs from the adaptive
retrieval implementation. Beating it does not alone establish routing quality.

## Freeze before execution

1. Improve implementations and select thresholds on the 29 development questions;
   select the final configuration once using the 29 validation questions. Give
   baselines the same development opportunity. Do not tune against hidden answers.
2. Freeze source, experiment configuration, model identifier, dependency versions,
   graph snapshot, vector index, scoring rules, and this protocol. Keep the same
   model, answer prompt, generation settings, corpus, and infrastructure across
   systems. Record intentional differences such as deterministic graph answers.
3. Use an input containing only `id,question` for seven systems. Supply only
   `id,question,expected_retrieval_route` to the oracle. The existing file called
   hidden_test_questions contains route labels, templates, and evidence metadata;
   do not assume its filename guarantees blinding. Never regenerate the split.
4. Use a fresh output directory. Never merge old preview-model results with new
   results. Preserve failed attempts and keep a fixed retry policy. Disable LLM
   response caching for timing measurements. Record service throttling and warmup.

## Main experiment and decision rule

Run all 242 questions for each of the eight systems: **1,936 outputs per repeat**.
Use three repeats if feasible (5,808 outputs), selected before execution. Report
the number actually completed. Randomize system order with a recorded seed; for
strong timing comparisons use balanced execution blocks and identical warmup.
Repeated outputs are not independent questions: average within question before
paired inference. All systems must have the same question/repeat keys. Reject
incomplete comparisons rather than silently retaining only successful pairs.

Primary endpoint: mean `answer_accuracy` using the frozen existing evaluator.
Report entity F1 and required-fact coverage as secondary quality measures, plus
error/abstention rates, evidence recall, median and p95 latency, and measured
tokens where available. Missing token telemetry is unavailable, not zero cost.
Do not substitute lexical similarity for factual correctness or automated
hallucination scores for blinded human assessment.

For the seven proposed-versus-comparator primary contrasts, report paired mean
differences, question-level bootstrap 95% intervals, Wilcoxon tests, and Holm
correction across those seven contrasts. A superiority claim for a comparator
requires a positive difference and Holm-adjusted p < .05. Report ties and losses.
Only claim superiority over all seven if all seven meet that rule. Treat the
six deployable-baseline comparisons and oracle reference distinctly in prose.
Secondary metrics and subgroup analyses are descriptive/exploratory; do not
select the winning metric after viewing results. The existing statistics script
corrects all pairwise comparisons and can be retained as a conservative broader
family, clearly labeled rather than presented as the seven-contrast family.

## Make adaptive routing the central mechanism analysis

Main-table comparisons do not isolate routing because systems differ in other
ways. In a separate ablation table, reuse the adaptive implementation with
`--no-routing` (always hybrid), `--no-vector` (graph), and `--no-graph` (vector).
These are variants of the proposed system, not replacements for any of the eight.
First run and select on development/validation. After freezing, evaluate the
prespecified variants on the same 242 questions without subsequent tuning.
The existing `--no-routing` also disables confidence-driven strict validation;
describe this as removal of the routing policy, not a pure route-choice-only
intervention. Do not attribute fallback/template effects solely to routing.

Report:

- Strict agreement with the existing gold route labels, a graph/vector/hybrid
  confusion matrix, per-route precision/recall/F1, and macro F1. The current
  relaxed metric accepts every route in two categories; retain it only as a
  separately named legacy metric. Category-derived gold labels are proxies,
  not demonstrated optimal per-question retrieval actions.
- Selected route, preferred route, confidence band, fallback use, actual evidence
  sources, and graph/vector retrieval counts. Separate intended route from
  executed fallback behavior. Confidence is a heuristic, not a calibrated
  correctness probability.
- Answer quality and latency by route, category, repository, hop count, and
  template coverage. Include all groups and their sample sizes, particularly
  repository/template holdouts; small subgroups are exploratory.
- Paired quality and latency differences against the routing-disabled variant.
  A routing benefit can be lower measured work/latency at comparable quality;
  any formal noninferiority margin must be chosen before the new run. Do not
  invent a post-hoc quality-minus-cost weight to force a favorable ranking.
- Optionally, a clearly labeled hindsight best-of-fixed-actions reference from
  matched ablation outputs. It is not deployable and is not the existing oracle.

## Execution

Prepare and inspect the frozen inputs and commands without API calls:

```powershell
python -m scripts.prepare_routing_evaluation
```

This writes a manifest, blinded inputs, and `run.ps1` under
`results/routing_evaluation_v1`. Run the generated script for the main eight
systems. It stops if coverage is incomplete or a runner records an execution
error. It then invokes the existing metrics and statistics pipeline. Use a new
output root for any revised configuration; do not overwrite a frozen experiment.

For routing-specific outputs after the main run:

```powershell
python -m src.evaluation.routing_diagnostics --results-dir results/routing_evaluation_v1/raw --output-dir results/routing_evaluation_v1/metrics
```

The diagnostic command requires all 242 questions for every system and matching
repeats. It does not replace the answer-quality evaluator or establish causal
routing benefits without the ablations. A prepared run is not a completed test.

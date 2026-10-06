# Evaluation v2 (frozen Phase 1 rules)

Gold is read-only. The scorer does not choose different rules for different systems or router variants.
`src/evaluation/metrics.py` remains the legacy module. `metrics_v2.py` is the new scorer.
Missing human gold is missing data, not an incorrect system answer. No human score is publishable until
the author supplies reviewed annotations. An explicit `answerable=false` is necessary for unanswerable items.
For legacy templates only, nonempty expected entities imply answerable when the label is absent.

| Category | Output type / extraction | Closed set? |
| --- | --- | --- |
| structure | File paths; normalize slash and leading `./`, preserve case | Yes |
| code_retrieval | File path/list, including extensionless paths; quoted symbols if explicitly annotated | Yes |
| documentation_lookup | Documentation file paths | Yes |
| dependency_analysis | `answer_type` selects files or commit hashes | Yes |
| developer_activity | Commit hashes or developer/count composite records | Hashes yes; composite records open |
| multi_hop | `answer_type` selects files or developer email identifiers | Yes |
| issue_pr_analysis | Bare/# issue numbers, full gold title strings, states, repository IDs, or composite records | Numbers/states yes; titles/repositories/composites open |

The `answer_type` field takes precedence over category. Human display categories are mapped to the
template names in code; source CSV values are preserved. Gold entities fall back to expected_answer
only when expected_entities is absent. JSON entity/fact lists must parse; malformed lists raise.

File/hash boundaries prevent `src/a.py` matching `wrong/src/a.py` or `src/a.py.bak`.
Repository names used as context are excluded from predicted file sets. File spelling is case-sensitive.
Prose titles are normalized for Unicode, whitespace and case and matched as complete gold strings with
boundaries; they are not split into incidental filenames or quoted fragments. Commit IDs are compared
by hash; a unique prefix of at least seven hexadecimal characters can match a full gold hash. Ambiguous
prefixes do not satisfy multiple entities. Commit repository identity is not independently validated by
hash comparison. Developer IDs strip `email:`. Composite number/title, title/state and developer/count
records require all components together on one line. Quoted symbols exclude dictionary keys followed
by a colon; arbitrary prose is not treated as a symbol.

Let G be the normalized expected entity set and P the set produced by the same extractor used for
accuracy. Precision = |G intersection P| / |P|; recall = |G intersection P| / |G|; F1 is their harmonic
mean. Empty predictions score zero on answerable gold. On error rows all three score zero.
For closed sets, strict accuracy requires recall=1 AND precision=1, equivalently F1=1 for nonempty gold,
plus successful execution, no abstention and no detected contradiction. Open sets require recall=1
plus the same guards; precision/F1 describe only recognizable entities, not arbitrary unseen prose.
Thus F1=1 is necessary but not sufficient for closed-set strict correctness when a contradiction or
abstention is detected. Explicit negation of a required entity and an unexpected asserted commit hash
when the question/gold establishes allowed hashes are contradiction guards. A right file plus a wrong
commit fails strict accuracy even though file-only F1 can remain one. These guards are deliberately
limited deterministic checks, not a semantic truth or faithfulness judge.

Open-vocabulary titles and explanations cannot support a complete extra-entity penalty from a gold-only
title matcher. This limitation must be disclosed; neither precision nor strict accuracy proves an
explanation free of fabricated prose. Closed expected sets can also be incomplete because the original
gold query used LIMIT; extra outputs are still errors against the frozen set, with no gold expansion.
Review the diagnostic changed-verdict list before interpreting such errors scientifically.

Required facts are evaluated one by one. An entity check is derived from the expected entities named
in that fact; a fact passes when all of its checkable expected entities are present. Question-context
entities such as the already-specified commit need not be repeated in a concise file answer. This gives
dependency_analysis-040 full fact recall for its ten returned files. A fact naming no checkable expected
entity is flagged, excluded from the fact denominator, and listed; all-uncheckable facts produce N/A.
If required_facts is absent, entity recall is the explicitly documented fallback. This measures required
entity coverage, not independently validated relations or causal explanations.

Abstention detection matches explicit uncertainty phrases, not arbitrary occurrences of words inside
issue titles. On answerable rows, abstention_rate is abstentions/all answerable rows. On unanswerable
rows, correct_abstention_rate is valid abstentions/all unanswerable rows; fabrication_rate is non-error
fabricated responses/all unanswerable rows. Execution errors form a separate outcome and cannot count
as correct abstention. Empty answers, exhausted/terminal model errors, retrieval errors, or parse failures
are errors, even if system code swallowed a failure. The harness stores an empty answer and separate
error fields, never an error message as an answer. Historical swallowed failures absent from saved logs
cannot be reconstructed and are a limitation of the diagnostic rescore.

Summary strict accuracy includes all scorable active rows, including execution errors as zero.
accuracy_non_error is a separate conditional statistic. n_errors, n_abstained, n_missing_gold and
n_scorable are reported separately. Superseded attempts and warm-up rows are retained but excluded
from main summaries. Prior failed attempts remain available for reliability analysis.
Legacy accuracy is the old expected-string containment rule, labeled legacy_accuracy; it is not strict.

Evidence precision/recall/MRR are N/A (empty CSV cells) for Plain LLM or route=none. They are also N/A
when gold evidence is missing. Other retrieval evidence comparisons reuse the legacy canonical ID
matcher and must not be confused with entity/answer correctness. Missing measurement is never zero.

The harness logs retrieval time, API attempt time, pacing/backoff waits, total wall time and residual
overhead. Analysis latency = total_wall_s - sleep_wait_s. Only non-error, non-retried, non-cache-hit rows
enter the reported latency mean/sample SD. Every requested repeat is retained with its run_id;
--discard-first-run excludes repeat one, so five requested repeats leave four measured repeats.
Accuracy repeat mean/sample SD is computed from repeat-level accuracies. API seed is recorded as null
because the existing systems never configured a generation seed; benchmark seeds remain in the config.

Responses are cached by model, prompt SHA-256 and generation parameters, in per-run/per-repeat cache
directories. Crash resumption can reuse a response; a fresh repeat never borrows an earlier repeat's
answer. Cached rows are labeled and excluded from latency. --no-cache disables reads and writes.
Provider aliases may change over time: the configured alias is recorded, not claimed as an immutable
model revision. SDK internal retries are disabled so application attempt logs describe every request;
application retries keep the configured budget. A finite 60-second HTTP timeout is explicit and logged.

Diagnostic rescores of old answers are not reruns, do not repair historical telemetry, and are not paper
results. No bootstrap or paired significance claims are introduced in Phase 1.

# Phase 2 — no-templates router selection

Date: 2026-10-13 (Asia/Colombo).

Route measurement status: **STOPPED_INFRASTRUCTURE_OR_UNKNOWN**. **114/140** questions have all three usable route outcomes. No Phase 3 work or held-out answer evaluation was performed. Gold and split contents are unchanged.

## Protocol and post-hoc amendment

The user selected no-templates with fresh uncached route measurements. The accepted 140-question Phase 1C split is preserved, with 20 questions per category, six repositories including Airflow, and its documented post-hoc detectable-subject audit. SHA-256: `b46e373f1b9ac2ce3a868ca62cab09589f0540cac6089f713c493fd083d634f6`.

After 33 outcomes, hybrid generated invalid `ENDS_WITH` for `router-tuning-196f6b2ad2abeb00`. The old all-clean policy stopped collection. On 2026-10-13 the user explicitly authorized a **post-hoc policy amendment**: retain genuine system errors as incorrect and include their execution cost; retry only infrastructure failures. The original error and all 33 original outcomes are preserved. Unknown failures stop for classification. No resampling until a model error disappears.

The amended oracle chooses minimum measured latency among non-error correct routes; exact ties use graph, vector, hybrid. This differs from Phase 1C's ordinal cost policy. Errors cannot become correct oracle labels. All questions, including no-correct-route questions, remain in accuracy/regret denominators.

No registered templates or deterministic answers; identical generator, evidence budgets and answer prompt across forced routes; cross-route fallback disabled during collection. Pacing/backoff are excluded from latency. Cache hits and infrastructure-contaminated outcomes cannot supply selection timings. Every route is checkpointed with an append-only attempt journal.

The outside-sandbox preflight passed: populated Neo4j, verified non-diagnostic index, and local `qwen2.5:7b`. The user subsequently confirmed **Gemini for the LLM router**, matching the Phase 2 brief. The CV script uses Gemini and caches router responses; Ollama is not the selected router provider. An earlier local router smoke test overlapped early route collection: timings are single-run observations on a shared workstation, not isolated performance benchmarks.

The first full suite passed 65 tests. After the amendment, seven measurement tests passed, including three new cases for error retention, infrastructure classification and unknown failures. Original and amended policies/snapshots are preserved. See [protocol](../results/v2/phase2/resumption_20261013/protocol.md) and [selection rule](../results/v2/phase2/resumption_20261013/selection_rule.json).

## Route outcomes

Tables below use only questions with all three policy-usable routes. Partial rows and all attempts remain in the raw journals; incomplete coverage is not a full-split result. Strict accuracy is restricted to `gold_complete=true`.

| Category | Route | n | Recall | Strict | Strict n | Errors | Mean execution seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ALL | graph | 114 | 0.3947 | 0.4468 | 94 | 2 | 2.538 |
| ALL | vector | 114 | 0.1228 | 0.1489 | 94 | 0 | 1.446 |
| ALL | hybrid | 114 | 0.2105 | 0.2553 | 94 | 2 | 3.006 |
| code_retrieval | graph | 20 | 0.7500 | 0.7500 | 20 | 0 | 2.514 |
| code_retrieval | vector | 20 | 0.2000 | 0.2000 | 20 | 0 | 1.521 |
| code_retrieval | hybrid | 20 | 0.5000 | 0.5000 | 20 | 0 | 2.759 |
| dependency_analysis | graph | 20 | 0.2500 | 0.2500 | 20 | 0 | 2.842 |
| dependency_analysis | vector | 20 | 0.0000 | 0.0000 | 20 | 0 | 1.406 |
| dependency_analysis | hybrid | 20 | 0.0000 | 0.0000 | 20 | 0 | 2.903 |
| developer_activity | graph | 10 | 0.0000 | 0.0000 | 7 | 0 | 2.885 |
| developer_activity | vector | 10 | 0.0000 | 0.0000 | 7 | 0 | 1.528 |
| developer_activity | hybrid | 10 | 0.0000 | 0.0000 | 7 | 0 | 4.021 |
| documentation_lookup | graph | 20 | 0.6500 | 0.6500 | 20 | 2 | 2.815 |
| documentation_lookup | vector | 20 | 0.2500 | 0.2500 | 20 | 0 | 1.529 |
| documentation_lookup | hybrid | 20 | 0.3000 | 0.3000 | 20 | 2 | 3.045 |
| issue_pr_analysis | graph | 15 | 0.6667 | 0.8750 | 8 | 0 | 2.791 |
| issue_pr_analysis | vector | 15 | 0.2667 | 0.5000 | 8 | 0 | 1.331 |
| issue_pr_analysis | hybrid | 15 | 0.2667 | 0.5000 | 8 | 0 | 2.831 |
| multi_hop | graph | 9 | 0.1111 | 0.1250 | 8 | 0 | 2.648 |
| multi_hop | vector | 9 | 0.1111 | 0.1250 | 8 | 0 | 1.347 |
| multi_hop | hybrid | 9 | 0.1111 | 0.1250 | 8 | 0 | 2.971 |
| structure | graph | 20 | 0.0500 | 0.0909 | 11 | 0 | 1.567 |
| structure | vector | 20 | 0.0000 | 0.0000 | 11 | 0 | 1.417 |
| structure | hybrid | 20 | 0.1500 | 0.2727 | 11 | 0 | 2.955 |

| Measured cheapest-correct route | Questions |
| --- | --- |
| graph | 28 |
| vector | 14 |
| hybrid | 7 |
| none | 65 |

| Recorded failure class (all active rows) | Outcomes |
| --- | --- |
| infrastructure | 1 |
| none | 340 |
| system | 4 |

### Infrastructure interruption

The continuation stopped on provider/transport failure. Affected timings are excluded from oracle selection. The append-only history preserves failed attempts; previously usable outcomes are not rerun.

| Question | Route | Attempt | Error | Provider status codes |
| --- | --- | --- | --- | --- |
| router-tuning-66cae5d00fc8017b | hybrid | 2 | ServerError | ['503', '504'] |

## Selection and freezing

Cross-validation and threshold sweep are not yet available. The unchanged selection priorities maximize estimated latency savings subject to mean recall regret <=0.02, then macro-F1, simpler variant, and lower tau. No missing result is treated as zero.

**No router is frozen.** Live old-adaptive/new-router comparison is not yet available.

**Phase 2 is incomplete and stopped on infrastructure failure.** Two continuation attempts at the pending hybrid measurement encountered Gemini 503/504 errors. Neither attempt supplies a usable selection timing. No model switch, timeout change or gold change was made. Resume only after provider availability recovers using `python -B scripts/measure_phase2_routes.py`; the checkpoint skips usable outcomes. No background measurement process remains running at this handoff.

Pending work: finish route measurements; run Gemini-router five-fold CV and the offline threshold sweep; produce variant comparisons and misrouted examples; integrate and test the selected configuration and held-out frozen-config guard; run the old/new live tuning-only comparison if selection succeeds. The deployment loader's existing Ollama branch also needs Gemini support before deploying an LLM selection. No selected YAML or completed freeze is claimed.

Continuation verification: seven measurement-policy tests and ten router tests passed with Python unittest (17 total). These cover the current components, not the pending deployment integration. Pytest was unavailable; no package installation was needed.

## Files and reproducibility

- `src/llm.py`
- `tests/test_llm_retry_status.py`
- `docs/router_selection_rule.md`
- `scripts/measure_phase2_routes.py`
- `tests/test_phase2_measurements.py`
- `reports/phase2.md`
- `results/v2/phase2/resumption_20261013/selection_rule.json`
- `results/v2/phase2/resumption_20261013/train_current.py`
- `results/v2/phase2/resumption_20261013/render_report.py`
- `results/v2/phase2/resumption_20261013/check_local_router.py`
- `results/v2/phase2/resumption_20261013/check_provider.py`

All generated measurements, logs, snapshots, tests, catalog provenance and prior documents are under `results/v2/phase2/resumption_20261013/`. Files contain complete contents, not diffs. No redundant ZIP archive is created.

## Blocker repair — 2026-10-13

The user requested a blocker fix. A minimal non-benchmark prompt (`Reply with OK.`) also returned HTTP 504, showing that the observed failure does not depend on repository retrieval or a large evidence prompt. Google documents 503 as service unavailability and 504 as a deadline failure: [official troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting). This identifies the failure class, not the underlying cause inside Google's service.

The local retry classifier depended on English message text and did not recognize numeric 504 with `DEADLINE_EXCEEDED`. It now treats explicit HTTP 408/429/500/502/503/504 as retryable, keeps nonretryable HTTP statuses terminal, and retains the existing six-attempt cap, backoff accounting, timeout, model and generation parameters. Six new tests, ten harness tests and seven measurement-policy tests passed (23 total).

This is a disclosed transport-handling amendment, not a change to answering or scoring. Original complete source files are preserved in `provider_recovery/before_fix/`. Future measurement snapshots use `route_outcomes/transport_fix_v1/`, binding the previous `policy_v2` snapshot by hash; old snapshots and outcomes remain intact. Infrastructure-contaminated timings remain ineligible even if an in-call retry succeeds.

Latest isolated health result: `{"ok": false, "model": "gemini-flash-lite-latest", "error_type": "ServerError", "wall_s": 61.003842500002065, "terminal_exception": "CallBudgetExceeded", "provider_status_code": 504, "n_attempts": 1}`. Diagnostic attempts are stored separately in `provider_recovery/events.jsonl` and are not evaluation rows. A retry repair cannot restore an unavailable upstream service; no successful recovery is claimed unless the health result and subsequent benchmark call succeed.

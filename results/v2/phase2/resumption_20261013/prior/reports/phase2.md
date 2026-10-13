# Phase 2 - implementation complete; empirical execution in progress

Date: 2026-10-09 (Asia/Colombo).

Phase 2 is **not yet empirically complete**. The router, fallback, training/oracle scripts and tests now exist. No tuning results, chosen variant, selected threshold or frozen model are claimed. No gold answers, old split memberships, historical experiment results, original router or baseline implementations were changed. Existing `.review_tools` deletions were left alone.

## Implemented fixes

- Added a separate `adaptive_hybrid_graphrag_v2` system so the original adaptive system remains available for comparison.
- Explicit graph/vector/hybrid scores use resolved KG entities, relation, multi-hop, aggregation, explanatory and semantic cues, plus similarity to fixed exemplars. All three routes are reachable in tests.
- Implemented rule, embedding kNN, standardized logistic regression and JSON-output local LLM router variants. The LLM router targets `qwen2.5:7b`; malformed output raises an error.
- Low top-route confidence selects hybrid. Empty/invalid graph evidence and empty/low-score vector evidence trigger logged hybrid escalation. Prior execution errors remain errors after recovery.
- Exposed tau in configuration. Frozen deployment checks the selected configuration checksum, entity catalog fingerprint, feature schema, exemplars and embedding model. The fallback score threshold is frozen too.
- Implemented graph-verified fresh router-tuning generation, excluding Airflow and rejecting normalized question or full expected-entity-set overlap with all existing splits. Existing sets are used only for exclusion checks, never substituted for tuning.
- Implemented forced graph/vector/hybrid outcomes, per-question maximum oracle accuracy, cheapest-correct labels from clean timings, category-stratified five-fold training, and the offline threshold sweep.
- Recorded the selection rule before any empirical router outcomes: maximize latency savings including routing overhead among candidates with mean recall-accuracy regret at most 0.02; then macro-F1, simpler variant, lower tau. If no candidate qualifies, freezing fails.
- Added recall accuracy alongside strict accuracy, nullable query-provenance-derived gold completeness, and strict accuracy on known-complete gold only. Reaching a query LIMIT remains unknown completeness; references are unchanged.
- Corrected environment verification to reject an empty graph, a diagnostic index and absence of the exact local model tag. Index rebuild invocation snapshots now permit resuming valid embedding checkpoints while retaining each invocation's configuration.

The protocol, feature definitions and limitations are in [docs/router_v2.md](../docs/router_v2.md). The machine-readable predeclared policy is [docs/phase2_selection_rule.json](../docs/phase2_selection_rule.json).

## Verification

`python -B -m unittest discover -s tests -v` passed all 48 tests. These cover route reachability, threshold escalation, KG entity resolution, vector/graph fallback, no-fallback behavior, supervised scores, malformed LLM output, frozen-config checks, oracle dominance/cheapest selection and gold completeness, plus the existing harness and metric regression tests. Unit fixtures do not establish empirical routing performance.

## Current external prerequisites

| Requirement | Observed state |
| --- | --- |
| Neo4j | Network connectivity succeeds, but the configured database has no nodes/labels. |
| Data loading | User authorization received; the approved MERGE-based load is in progress. |
| Vector index | The full manifest-backed rebuild has completed. Hash verification is pending the post-load environment check. |
| Local model | Ollama is reachable and `qwen2.5:7b` is installed. |
| Gemini | Key present; user authorized transmission of fresh tuning questions and repository evidence. |
| Fresh tuning data | Not generated: requires the populated graph. |

Connectivity evidence is [environment_network_current.json](../results/v2/phase2/environment_network_current.json). Its raw empty `label_counts` observation predates the verifier fix and must not be interpreted as a usable graph. The index build runs locally in the background and saves resumable embedding checkpoints under `results/v2/vector_index/`; it is not a completed index until its manifest exists.

## Results still required

Oracle route distribution and vector-cheapest rate, four-variant cross-validation results, threshold sweep measurements, selected configuration, empirical misroutes and old-adaptive versus V2 comparison are unavailable. Unavailable does not mean zero. No existing test/human split, template route label or diagnostic index was used to manufacture these results.

Offline fallback latency is explicitly an estimate: initial retrieval plus the stored hybrid runtime. The eventual live comparison remains necessary. Five-fold results used for selection are tuning results, not held-out paper results. Graph and model execution failures block clean oracle cost selection rather than counting as fast answers.

## Changed source and documentation files

- `config/experiment.yaml`
- `src/systems/router_v2.py`
- `src/systems/adaptive_hybrid_graphrag_v2.py`
- `src/systems/ollama_router_client.py`
- `src/evaluation/metrics_v2.py`
- `src/vector_store.py`
- `scripts/run_eval.py`
- `scripts/verify_environment.py`
- `scripts/prepare_router_tuning.py`
- `scripts/derive_oracle_routes.py`
- `scripts/train_router_v2.py`
- `scripts/compare_router_v2.py`
- `tests/test_router_v2.py`
- `tests/test_gold_completeness.py`
- `docs/router_v2.md`
- `docs/phase2_selection_rule.json`
- `reports/phase2.md`

Complete contents, not diffs, are supplied in [phase2_complete_files.zip](../results/v2/phase2/phase2_complete_files.zip). New generated artifacts are confined to `results/v2/`, except the requested report and source/docs. The index checkpoints are binary build artifacts rather than source changes.

## Authorization and continuation

The user authorized the configured database load and Gemini use on 2026-10-09 ("allow and load the db"). The previously rejected MERGE loader was approved and is now running. The full vector index has completed with 131,179 chunks; its hashes and the loaded graph will be verified before tuning. The earlier authorization block is resolved.

After the load: verify the graph/index, generate the fresh disjoint tuning split, collect forced-route outcomes, run the predeclared comparison and sweep, freeze only a qualifying configuration, run the live old/new comparison, and replace this pending-results section with measured findings. Stop at Phase 2.

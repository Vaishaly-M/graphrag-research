# Router V2 protocol

The old classifier and adaptive system remain available for a fair fresh-set comparison.
The new system is `adaptive_hybrid_graphrag_v2`; it refuses normal deployment without a selected,
checksum-protected `results/v2/phase2/frozen_router.json` and the matching KG entity catalog.
This avoids calling a default, untrained configuration the selected router.

Features are the number of exact KG entities resolved in the question (capped at five), relation cues,
multi-hop cues, aggregation cues, explanatory cues, semantic/code/documentation cues, and maximum
embedding similarity to three fixed exemplars for each route. The resolver uses aliases actually
exported from Neo4j; finding a slash or keyword alone does not count as resolving a KG entity.
No route labels or reference answers are available to inference. Registered Cypher templates still
perform retrieval but do not dictate the new router's scores.

Variants: an explicit weighted rule with softmax scores; cosine-weighted kNN; standardized logistic
regression; and a JSON-probability LLM router using the local `qwen2.5:7b` tag. Rule and LLM prototypes
are fixed before evaluation. kNN/logistic train inside each category-stratified fold on empirical
cheapest-correct labels only. Classes absent from a training fold are recorded, not invented.
The scores are decision scores; probability calibration has not been established.

`tau` is exposed in RouterV2, config/experiment.yaml's router_v2 section, and the selected frozen JSON.
An unselected constructor uses the YAML default. A frozen runtime uses the frozen tau, so editing the
YAML default cannot silently alter a selected configuration. Below tau, choose hybrid. All three
routes are reachable in unit tests; that is not a claim about their empirical frequencies.

For a single-source route, an empty/invalid graph result or empty/low-score vector result escalates to
hybrid. Both the selected and executed routes, fallback reason, scores, features and evidence counts
are stored. The vector floor is 0.30 cosine similarity, an operational safety threshold rather than
a calibrated probability. Graph low confidence means its existing evidence validator rejected it.
No-fallback/no-graph/no-vector ablations disable incompatible escalation. Exceptions still propagate
to measurement error accounting; successful fallback does not erase a prior execution error.

Phase 1B decisions carried by the accepted reports require a new router-tuning split. The preparation
script uses seed 20261009 and fresh graph-verified questions, excludes Airflow, rejects exact normalized
question and complete expected-entity-set overlap with every existing split, and retains all old gold.
Those exclusion reads are for disjointness, not training. A fixed seed alone cannot ensure graph query
ordering or model determinism; the materialized CSV hash is the reproducibility boundary.

The predeclared selection rule is docs/phase2_selection_rule.json. Only the new tuning set is used.
Forced graph/vector/hybrid runs share the new system's retrieval/answering implementation with safety
escalation disabled, so the oracle does not inherit category labels. No-correct-route items have a null
oracle label and zero oracle best accuracy. Missing/error/cache/retried latency cannot identify a
cheapest correct route and therefore blocks selection rather than being treated as fast success.

Offline threshold evaluation reuses out-of-fold scores and stored route answers. A simulated safety
fallback uses the hybrid outcome and charges the initial retrieval plus hybrid runtime. This is a
conservative estimate; it is not an end-to-end live measurement. Routing overhead includes feature
extraction and classifier work. Training cost is excluded. Five-fold category stratification keeps
supervised artifact fitting inside the fold. The same OOF sweep selects hyperparameters, so its numbers
are tuning results, not an unbiased held-out estimate.

The metric layer now exposes recall_accuracy alongside strict_accuracy. Recall accuracy requires all
expected entities without the closed-set extra-entity penalty (explicitly negated targets still fail).
gold_complete is nullable and provenance-derived: a supported generation query without LIMIT, or fewer
answers than one literal LIMIT, indicates a complete query result; reaching LIMIT is unknown rather
than proof of incompleteness. Complex limits and missing query provenance remain unknown. This does
not certify semantic gold exhaustiveness. strict_complete_accuracy reports strict accuracy only on
known-complete query results; original strict and gold data are retained unchanged.

Continuation after environment and data-transfer approvals:

```powershell
python -B -m src.build_vector_index
python -B scripts/verify_environment.py --output results/v2/phase2/environment_verified.json
python -B scripts/prepare_router_tuning.py
python -B scripts/derive_oracle_routes.py
python -B scripts/train_router_v2.py
python -B scripts/compare_router_v2.py
```

Do not skip a failed gate, substitute the diagnostic index, substitute an existing evaluation split,
or fabricate a frozen model when selection fails. Graph loading is a separate explicitly authorized
operation because it uploads repository data to the configured database.

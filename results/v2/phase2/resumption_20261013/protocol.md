# Phase 2 resumption protocol ? 2026-10-13

User authorization: continue Phase 2; explicitly selected no-templates and fresh clean route measurements.

Use the accepted 140-question router-tuning v2 split, including Airflow; do not regenerate it. No hidden-test or human-test answers are accessed. Phase 1C outcomes remain diagnostic and unchanged.

The selection rule is copied to selection_rule.json with a dated amendment for the accepted split size and mode. Regret bound, variants, folds, thresholds and selection priorities are unchanged. Unlike the Phase 1C ordinal oracle, Phase 2 labels use minimum clean measured latency among correct routes, with graph/vector/hybrid order only for exact ties.

Collect 420 fresh forced-route outcomes through the same V2 system, disabling template queries, deterministic shortcuts, cross-route fallback and response-cache reads. Warm retrieval before timing. Preserve shared generator, answer prompt, evidence budget and retrieval parameters in the config snapshot. Exclude pacing/backoff. Stop on any error, retry-contaminated timing or quota failure, saving the completed attempt. A later explicit invocation resumes clean outcomes and retries only unclean/missing outcomes, retaining every attempt. No quality-based retries of clean incorrect answers.

Four unit tests cover measured-cost selection, cost ties, refusal of errors/cache/retries, and incomplete/no-correct labels. Initial launcher validation rejected the spelling of the accepted audit status before any model calls; corrected to PASS_DETECTABLE_SUBJECTS.

No CV, threshold sweep, model freeze or live comparison is claimed until all clean route timings exist. The prior report and selection policy are preserved in prior/.

## User-approved error-policy amendment, 2026-10-13

Post hoc after 33 outcomes and one generated-Cypher syntax error: keep genuine system failures as incorrect and include their pacing/backoff-excluded execution cost. Retry only identifiable infrastructure failures, including provider availability, transport, DNS and quota failures. Stop on unknown failures instead of assuming they are retryable. An infrastructure retry contaminates a timing even if the final call succeeds. No cached timings. Existing inference source, model settings, split and all 33 original outcomes are unchanged. Original snapshot remains in place; policy_v2/config_snapshot.json records continuation. Original system errors are not sampled again. Errors during initial retrieval remain incorrect after fallback in the offline sweep.

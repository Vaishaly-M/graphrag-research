# Router selection rule - transcription of the recorded Phase 2 policy

Written on 2026-10-13 before this continuation runs cross-validation or the threshold sweep.
This document transcribes the already-recorded policy; it does not claim the policy was first
chosen today or before the historical route measurements. The source policy and its disclosed
post-hoc amendments remain unchanged.

Only the accepted router-tuning split may supply training data, exemplars, labels or selection
results. Do not evaluate hidden-test or human-test. Preserve the no-templates measurement track.

Use five category-stratified folds, seed 20261009, and rule, embedding-kNN, logistic, and LLM
router variants. Store out-of-fold scores once. Sweep tau = 0.55, 0.60, 0.65, 0.70, 0.75, 0.80,
0.85, 0.90 and 0.95 offline. Confidence below tau selects hybrid. Evidence-triggered escalation
must be included and recorded separately from confidence-threshold routing.

## Fixed selection objective

Require mean recall-accuracy regret <= 0.02 over all 140 questions, including questions for
which no route is correct. This bounds average loss against the measured per-question oracle
to two percentage points (at most two lost binary-correct answers on this split). This small
budget permits a latency tradeoff without accepting a large loss of answer coverage; it is a
tuning constraint, not a held-out guarantee.

Among eligible candidates, maximize mean latency savings against always-hybrid after measured
routing overhead. Break ties by higher routing macro-F1, then rule, knn, logistic, llm, then
lower tau. If no candidate satisfies the bound, do not freeze a router or relax the bound.
This preserves the recorded objective; it is not a new accuracy/latency-ratio optimization.

The oracle selects the non-error correct route with minimum measured execution latency;
exact ties use graph, vector, hybrid. This is the recorded Phase 2 amendment, not Phase 1C's
ordinal route-cost oracle. Genuine system errors remain incorrect with their measured cost.
Infrastructure failures and cache-hit timings cannot supply selection labels. Unknown failures
stop for classification. No resampling of a genuine system error to obtain a better answer.

Report recall accuracy on all questions and strict accuracy with its gold-completeness scope
and denominator. Report routing-label metrics only on questions with a defined oracle label,
and disclose their denominator. Include all questions in answer accuracy and regret.
Offline escalation latency is an estimate based on independent forced-route observations;
only a later live comparison can measure the deployed pipeline's actual latency.

Source policy SHA-256: `beb4512738118a3cce42d09849ace7148c96f1bde8d3c4dddbfc8f9fcb05bcc9`.

Tuning split SHA-256: `b46e373f1b9ac2ce3a868ca62cab09589f0540cac6089f713c493fd083d634f6`.

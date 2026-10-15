# Metrics and latency protocol

Implementation: `src/eval`. Tests: `python -m pytest tests/test_eval_phase4.py`. The older `src/evaluation` package is retained for historical reproducibility and is not this protocol.

## Entity normalization

Values must be explicit strings, not entities selected by searching the gold inside free-form answers. Apply Unicode NFC and trim outer whitespace. Case is preserved by default (repository paths and symbols are case-sensitive); optional case-folding is a recorded configuration choice. Standalone paths convert backslashes to slashes and remove leading `./`; code/prose with whitespace is not rewritten. `issue 0012`, `Issue #12`, `#12` normalize to `12`. Bare `12` already has that form. SHA-like hexadecimal identifiers with at least one a–f letter are lowercased and truncated to 12 characters (configurable 7–40). Shorter prefixes do not match longer ones; two distinct full SHAs sharing the configured prefix raise an error. All-digit strings remain numbers. Duplicates collapse into sets. Evidence IDs are exact canonical IDs without these answer transformations.

## Correctness

For predicted set P and gold set G, let h=|P∩G|. Precision=h/|P|, recall=h/|G|, F1=2PR/(P+R). Zero denominator conventions: empty predictions have precision 0 unless gold is also empty; empty gold has recall 1; both empty have P=R=F1=1. An explicit abstention is distinct from an answerable empty set.

STRICT set accuracy is 1 iff recall=1 and precision≥τ (default τ=0.8), and the system did not abstain. Single-value answers require exact normalized set equality with one gold value. LENIENT coverage is 1 iff recall=1 regardless of extra values, except an abstention on an answerable question is always incorrect. For unanswerable items, both correctness indicators are 1 only for an explicit successful abstention; entity metrics are N/A. Failed API calls cannot earn abstention credit. Unknown/unverified gold is rejected.

| Example | Gold | Prediction | P | R | F1 | Strict | Lenient |
|---|---|---|---:|---:|---:|---:|---:|
| Extra entities | a,b | a,b,c,d | .5 | 1 | .6667 | 0 | 1 |
| Threshold boundary | a,b,c,d | a,b,c,d,e | .8 | 1 | .8889 | 1 | 1 |
| Single value plus extra | a (single) | a,extra | .5 | 1 | .6667 | 0 | 1 |
| Unanswerable | not found | abstention | N/A | N/A | N/A | 1 | 1 |
| Over-abstention | a | abstention | 0 | 0 | 0 | 0 | 0 |

Lenient coverage resembles the old reported accuracy and can reward verbose answers with low precision. Strict accuracy controls that failure for set answers; F1 continuously measures the precision/recall balance. Reports use per-question macro means and explicit metric denominators, keeping question sets and splits separate.

## Ranked retrieval and abstention

Deduplicate ranked evidence by first occurrence. Recall@k=|top-k∩gold evidence|/|gold evidence|. MRR per question is 1/rank of the first relevant item, or 0 if none. DCG@10=Σ rel_i/log2(i+1), i=1..10, with binary relevance. nDCG@10=DCG/ideal DCG for min(10, number of relevant evidence IDs). These metrics run for every adapter returning a ranked list. Empty list means retrieval failed (0); `None` means no retrieval capability (N/A). Empty gold evidence has N/A retrieval metrics. Canonical repository nodes included in gold count as relevant evidence; they are not silently omitted.

Not-found rate = successful abstentions / unanswerable questions. Over-abstention rate = successful abstentions / answerable questions. A denominator of zero yields N/A. Operational errors stay in accuracy denominators as incorrect, and are logged separately.

## Faithfulness hooks

`ClaimExtractor.extract` and `Judge.judge` are interfaces only until Phase 10. Each claim receives supported, unsupported or uncertain. Faithfulness=supported/claims; unsupported-claim rate=unsupported/claims; uncertain remains in the denominator. No claims means N/A. With no judge, scores are N/A and status is `not_implemented`. The judge's normalized family must differ from every declared generator family, including Qwen. No Gemini judge is implicitly invoked.

## Timing and retries

`time.perf_counter` times individual retrieval/generation attempts. Their totals include failed attempts but exclude retry waits. End-to-end time is elapsed question processing minus explicitly measured retry waits; raw wall time and excluded wait time are also saved. Throttle waits occur before starting each question, outside all question timers. Initialization/model loading before `run` is excluded; first-call lazy loading inside an adapter is included and must be considered when interpreting cold starts. Dry runs measure plumbing only.

Adapters must use one-attempt transports with SDK retries disabled and no internal sleeps. All retries must go through `Timing.call`; opaque legacy clients with hidden backoff are not compliant adapters. Retry events are fsynced to a separate JSONL immediately and repeated in the completed question record. Each event records stage, attempt, duration, exception type, status and whether another attempt is scheduled; exception text is omitted to avoid leaking credentials. Any retry, HTTP 429 or timeout contaminates the question. Contaminated and errored questions are excluded from latency means, retained for accuracy, and counted explicitly. Resume replays completed raw records without model calls; it does not pretend cached responses have fresh zero latency. An interrupted in-flight request may execute again because exactly-once external API execution cannot be guaranteed across crashes.

## Statistical helpers

McNemar uses an exact two-sided binomial test on discordant paired binary outcomes: b=A-only correct, c=B-only correct, X~Binomial(b+c,.5); no discordance gives p=1. Wilcoxon is two-sided on paired differences A−B, discarding zeros (`wilcox`) and assigning average ranks to ties through SciPy. All-zero differences give p=1. Paired bootstrap resamples question indices with replacement 2,000 times (seed 42) and reports the percentile 95% CI of the mean difference. Rank-biserial effect size=(W+−W−)/(W++W−), with average ranks of absolute nonzero differences; positive favors A, all zeros yields 0. Holm adjusted p-values are the cumulative maximum of (m−i+1)p_(i), clipped at 1 and restored to original order. Callers must align identical question IDs before supplying paired arrays; missing data must be handled pairwise, not independently.

## Harness and acceptance commands

Phase 5 adds an explicit Oracle evidence-replay flag. Oracle records that reuse the exact compared Adaptive evidence remain in accuracy statistics but are excluded from latency means; their measured time omits prepaid Adaptive retrieval work. Per-run YAML configuration files accompany raw JSONL.

An adapter exposes `name`, `model`, serializable `config`, and `answer(question, repo, timing=...)`. The model receives no gold, route labels or benchmark annotations. The result contains answer, explicit predicted entities, abstention, ranked canonical evidence IDs (or None), route and token usage. `--system module:factory` loads any compliant adapter. New provider transports should be injected into `PlainLLM`; the bundled fixture never calls a real model.

```powershell
python -m src.eval.harness --questions data/benchmark/template/development.jsonl --output runs/dryrun/phase4/plain.jsonl --run-id phase4-dev-1 --system plain_llm --dry-run --limit 10
python -m src.eval.harness --questions data/benchmark/template/development.jsonl --output runs/dryrun/phase4/stub.jsonl --run-id phase4-dev-1 --system stub --dry-run --limit 10
python -m pytest tests/test_eval_phase4.py tests/test_data_layer.py
```

Each JSONL has a sibling metrics JSON and Markdown table computed from saved raw rows. Repeating the same command resumes; changing run ID/config requires a separate output path. Cache identity includes system, model, configuration/source/question hashes, question ID and run ID. A torn final JSONL line is truncated; earlier corruption fails. Run one writer per output file. Test runs additionally require a freeze-v2 (or freeze-v2.x) tag at HEAD and a clean tracked tree. This phase does not create a freeze tag or run held-out tests.

# Router v2 validation

Development: 32 T questions. Validation: 32 T questions. P is not used for router training or selection. No test or H questions were read.

Selected C=10.0, tau=0.55, temperature=0.250004. Validation routing accuracy: 71.8750%.

Rows are gold; columns are chosen routes after confidence fallback.

| Gold / chosen | graph | vector | hybrid |
|---|---:|---:|---:|
| graph | 16 | 0 | 0 |
| vector | 4 | 1 | 3 |
| hybrid | 2 | 0 | 6 |

| Category | Correct | Count | Accuracy |
|---|---:|---:|---:|
| issue_pr | 4 | 4 | 100.0000% |
| developer_activity | 8 | 8 | 100.0000% |
| multi_hop | 10 | 12 | 83.3333% |
| documentation | 1 | 8 | 12.5000% |

Constant-majority validation baseline: 50.0000%. Training classes: {'graph': 20, 'vector': 4, 'hybrid': 8}. Validation classes: {'graph': 16, 'vector': 8, 'hybrid': 8}.

Unsupported training classes: []. No synthetic labels were invented. 

Calibration is development-only, using repository-grouped out-of-fold predictions. C and tau are selected on validation; reported validation accuracy is a tuning result, not an unbiased generalization estimate. Template families are disjoint between development and validation, but calibration folds share development families. The vector class has only four training examples.

Router v1 remains available through src.routing.router.RouterV1 and delegates to the unchanged historical rule implementation. Its confidence is heuristic, not calibrated.

The Phase 8 cache-replay sweep is implemented in analysis/routing_evaluation.py; no test sweep was run and no generation API was called.

Router comparison on the same 32 T validation questions: unchanged Router v1 accuracy=0.250000; fitted v2 accuracy=0.718750. V1 chose hybrid for every question. These are validation routing metrics, not answer metrics or held-out results.

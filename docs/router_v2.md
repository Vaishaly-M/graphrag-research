# Router v2

`analysis.train_router_rebuild` fits a deterministic logistic classifier on explicit question features plus pinned MiniLM sentence embeddings. Repository names are removed from question text. No generator API is called. Development repository-grouped out-of-fold predictions fit temperature calibration; validation selects regularization and confidence threshold. Below threshold, routing selects hybrid. `src.routing.router.RouterV1` preserves the original rule implementation.

The original data had 20 graph and 4 vector development labels, and 16 graph validation labels. The user approved a versioned supplement. `devval-supplement-1` adds eight development hybrid questions and eight each of validation vector/hybrid questions. Training uses the combined T files; P is optional and is not used in this router fit. The base benchmark files remain unchanged. `configs/splits.yaml` declares supplement paths and families separately. The explicit `--allow-missing-class` mode remains available for diagnostics, but is unnecessary for the complete supplement.

`analysis.routing_evaluation` computes route confusion and category accuracy and replays cached graph/vector/hybrid outputs for thresholds 0.55 through 0.95. It checks cache alignment and shared settings; no test sweep has been executed.

`python -m analysis.phase7_devval --run-id NAME` writes a plan using only T/P development and validation paths. Add `--execute` after router, vector tuning and Gemini access are ready. Runs preserve separate set/split outputs and execute Adaptive before Oracle for exact evidence replay. Empty P splits are reported explicitly. Failed runs stop the campaign for inspection. No automatic commit or freeze tag is created.

# Clean snapshot data layer

`configs/snapshots.yaml` pins five real repositories to their existing Git object SHAs and dates. No mutable working-tree files are read. `configs/splits.yaml` defines seed 42 and globally disjoint question families. Human counts remain pending the user's new CSV with gold.

Run from the workspace:

```powershell
python -B -m src.ingest.synthetic_snapshot
python -B -m src.ingest.snapshots
python -B -m src.kg.build
python -B -m src.kg.neo4j_store
python -B -m src.retrieval.build_indexes
python -B -m analysis.build_splits
python -B -m analysis.validate_data_layer --live
python -B -m analysis.validate_indexes
python -B -m analysis.report_data_layer
python -B -m unittest discover -s tests -p test_data_layer.py
```

`make all` runs the same data pipeline where Make is available. Credentials come from .env; none are saved to manifests. Public API fallback is available when a configured GitHub token is invalid. Rate-limit waits longer than 55 seconds stop with checkpoints, rather than silently reducing the dataset; resume the same command when capacity returns.

Embedding runtime dependencies are pinned in `configs/data_layer_dependencies.json`. The FP32 ONNX model is exported locally from the pinned MiniLM revision using `python -B scripts/probe_embedding_backend.py`; this also checks equivalence on synthetic strings with varying lengths and Unicode. Install `onnx==1.23.2`, `onnxruntime==1.31.0`, `protobuf==7.36.2` and `ml_dtypes==0.6.0` into workspace `.data_runtime` with pip `--target`. Install `onnxruntime-directml==1.24.4` separately into `.data_runtime_dml`; the two runtime packages share a Python namespace and must not overwrite one another. The final encoder uses the existing Intel GPU through DirectML, with fixed batches of 64 padded/truncated to 256 tokens. A short final batch is padded with empty inputs and the extra outputs are discarded. The original model revision must be in the Hugging Face cache. `configs/indexes.yaml` pins the exported artifact hash, tokenizer revision, maximum sequence length and runtime settings. Index construction and query encoding share this configuration and reject a mismatch. No quantization is used. A machine without the pinned provider must explicitly change configuration and rebuild the index, not silently substitute a runtime.

Git files are filtered for binaries, generated markers, lockfiles and build directories before graph/index construction. PyDriller provides commit metadata; path-only Git diffs avoid loading unnecessary full patches. Like PyDriller, merge commits have no modification edges. History is capped at the latest 1,000 reachable commits; issue and PR collections are capped at 300 each. Developer identities are scoped by repository and canonical email/GitHub numeric ID, without speculative account linkage.

GitHub metadata is an immutable observation, not the issue/PR state at the Git commit date. Pages are hashed, timestamped and checkpointed; collection follows server-provided cursor links and deduplicates overlapping pages. Issue-only search avoids scanning thousands of PR entries to locate sparse issues; incomplete search responses are rejected. The requested sample is below search's 1,000-result ceiling. See [GitHub's issue API](https://docs.github.com/en/rest/issues/issues) and [PyDriller's repository API](https://pydriller.readthedocs.io/en/latest/reference.html). Page observations can span a collection interval; this is not an atomic GitHub database snapshot.

Canonical nodes/relationships live under `data/graph_exports/rebuild-20261014`. Neo4j uses `DLRepository`, `DLFile`, `DLCommit`, `DLIssue`, `DLPullRequest`, `DLDeveloper` and `DL_*` relationships. IDs include dataset/snapshot scope; historical graph data is preserved. Retrieval integrations must use these labels and filter dataset/repository. Relationship validation compares exact stored directions and identities against exports. Constraints enforce unique IDs; lookup/full-text indexes are created and awaited before loading.

FAISS and the Okapi BM25 inverted index consume exactly one `chunks.jsonl`, with its hash stored in both manifests. Every chunk has repo, snapshot, commit and path keys; path is null for non-file metadata, which has no single filesystem path. File paths are preserved. Local embedding model artifacts and source exports are hashed. Embedding checkpoints are keyed by chunk and encoder-configuration hashes, so changing inputs cannot reuse stale vectors. `SnapshotIndex` requires an explicit repo for either search method. BM25 statistics are computed within the requested repository, preventing held-out repositories from influencing development scores.

Counts in `reports/kg_validation.md` and `reports/split_counts.md` are script-generated. Historical result directories and split files are not inputs to this rebuild. Planned P slots are not collected paraphrases; pending H slots are not fabricated human questions. Gold for T describes retained files and sampled history only, explicitly in each applicable question. This task does not run test-system answers or train a router.

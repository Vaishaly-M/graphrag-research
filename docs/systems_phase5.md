# Rebuilt systems

The clean implementations live under `src/systems/rebuild/`; the similarly named top-level legacy modules remain historical and are not entry points for the rebuilt experiment. All eight names instantiate the common `System` interface: `answer(question, repo, timing=...)`. The Phase 4 harness supports the adapter and saves a `.config.yaml` beside each raw JSONL. Every answer also includes the retrieval path, exact evidence sent to generation, effective route, token events and YAML configuration.

Run five development questions per system with:

```powershell
python -m src.systems.rebuild.smoke --dry-run --run-id phase5-dry-final
python -m analysis.tune_vector_rebuild
python -m src.systems.rebuild.smoke --run-id phase5-live-1
```

The dry-run calls the actual framework orchestration with offline transport and database fixtures. It is an integration test, not evidence of live model quality. Live smoke requires completed vector selection and uses Gemini 2.5 Flash, temperature 0.2, maximum output 1024 tokens, no SDK retries, and zero thinking budget. Throttle is outside question timers. Adaptive is explicitly provisional always-hybrid until Phase 6; the factory accepts a router callable for the final implementation.

The current account rejects Gemini 2.5 Flash generation despite listing the model. The user chose to retain that model and provide an account with access; live smoke is pending this change. No model migration is implicit. The generic `python -m src.systems.rebuild.run` CLI supports one named system on any explicit question set/split through the Phase 4 freeze and gold checks. Oracle requires matching `--adaptive-results` to retain the exact compared evidence; this replay excludes Oracle from live latency means.

Plain LLM receives the same answer prompt with an empty evidence list; its only task input is the question. All other systems use the same answer wrapper and settings. Graph template handling is limited to generic file/directory and commit identifier lookups, followed by LLM Cypher on no match/empty results. It does not import benchmark generation templates, gold Cypher, or H data. Graph facts are limited to 20 rows and 6000 serialized characters per evidence item, uniformly across systems; this truncation is a documented limitation. Unsupported generated Cypher fails visibly rather than executing unscoped queries.

LangChain uses the installed `langchain_community` 0.3.24 `Neo4jGraph` and `GraphCypherQAChain` (the older, deprecated but real integration). The chain performs Cypher generation and retrieval with `return_direct=True`; final synthesis is outside the chain to preserve the common answer prompt. Its Neo4jGraph subclass delegates to the shared scoped Neo4j driver. LlamaIndex uses `llama-index-core` 0.12.52.post1 `TextToCypherRetriever` and the real `Neo4jPropertyGraphStore` subclass from `llama-index-graph-stores-neo4j` 0.4.6, with raw-response metadata. It uses no index construction or custom imitation of the retriever. The store constructor is adapted to avoid schema sampling and schema-mutating framework initialization; queries go through the same read-only driver. Both frameworks receive the exact same declared DL schema.

The conservative Cypher subset permits a single bounded MATCH, known labeled nodes/relationships, WHERE, RETURN, ordering and LIMIT. It excludes procedures, subqueries, optional matches, WITH/UNWIND, variable-length traversals and mutations. The executor injects repository/dataset property constraints into every matched node. This restricts expressiveness, particularly aggregates requiring multiple clauses; it must be disclosed when comparing framework baselines. Framework references: [LangChain Neo4j integration](https://neo4j.com/labs/genai-ecosystem/langchain/), [LlamaIndex property-graph usage](https://developers.llamaindex.ai/python/examples/property_graph/graph_store/).

Vector tuning uses all retained chunks from the four development repositories, all 24 development questions, character sizes 400/800/1200, 15% overlap, k=5/10/20. FAISS and BM25 candidates are repository-filtered, fused by reciprocal rank (constant 60), limited to 40 candidates, and reranked with pinned `cross-encoder/ms-marco-TinyBERT-L-2-v2`. Evidence Recall@k is the selection objective; ties use nDCG@10, smaller k, then smaller chunk size. The full grid is checkpointed under `data/indexes/vector-development` and `runs/vector_tuning`; selection is not declared until all nine cells complete. These development indexes deliberately contain no Airflow. A selected full-snapshot index must be built before held-out evaluation; a development-only index must not be used as a test index.

See `reports/vector_tuning.md` for generated progress/results and `reports/oracle.md` for Oracle privileges and conditional bounds. Human questions, validation questions and test questions are not loaded by the tuning or smoke commands.

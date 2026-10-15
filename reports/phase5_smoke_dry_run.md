# Phase 5 smoke tests

Run: `phase5-dry-final`. Mode: OFFLINE FIXTURE (real framework orchestration, no quality claim).

| System | Questions | Passed | Errors |
|---|---:|---:|---:|
| plain_llm | 5 | 5 | 0 |
| vector_rag | 5 | 5 | 0 |
| langchain_graphrag | 5 | 5 | 0 |
| llamaindex_graphrag | 5 | 5 | 0 |
| fixed_graph_rag | 5 | 5 | 0 |
| fixed_hybrid_rag | 5 | 5 | 0 |
| adaptive_hybrid_graphrag | 5 | 5 | 0 |
| oracle_hybrid_rag | 5 | 5 | 0 |

Adaptive uses the explicitly provisional hybrid router until Phase 6. Oracle-Best-of-3 is a post-hoc artifact, not another model call. Raw JSONL, per-run YAML configs and metrics are under runs\phase5\phase5-dry-final.

Passing means all requests returned valid records without operational errors; it does not mean answers were correct.

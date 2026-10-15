# Vector tuning

Status: IN PROGRESS. Full four-development-repository corpus; no Airflow or H.

Character chunks; overlap 15%. Dense FAISS + BM25 RRF, then pinned cross-encoder. Retrieval-only selection; no answer-model or test feedback.

| Chunk | Overlap | k | Questions | Evidence recall | nDCG@10 |
|---:|---:|---:|---:|---:|---:|
| 1200 | 180 | 5 | 24 | 0.020833 | 0.016119 |
| 1200 | 180 | 10 | 24 | 0.045455 | 0.026155 |
| 1200 | 180 | 20 | 24 | 0.107955 | 0.026155 |
| 800 | 120 | 5 | 24 | 0.020833 | 0.012774 |
| 800 | 120 | 10 | 24 | 0.020833 | 0.012774 |
| 800 | 120 | 20 | 24 | 0.137121 | 0.012774 |

Selection: maximize macro evidence recall; ties nDCG, smaller k, smaller chunk. Canonical repository evidence nodes are not present in the text index and remain in the recall denominator.

Reranker: {"candidate_k": 40, "chunk_sizes": [400, 800, 1200], "k": 10, "ks": [5, 10, 20], "overlap_fraction": 0.15, "reranker": "cross-encoder/ms-marco-TinyBERT-L-2-v2", "reranker_revision": "81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc"}

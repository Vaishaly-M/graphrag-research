#!/usr/bin/env bash
set -euo pipefail
for s in plain_llm vector_rag langchain_graphrag llamaindex_graphrag fixed_graph_rag fixed_hybrid_rag oracle_hybrid_rag adaptive_hybrid_graphrag; do
  python -m src.systems.$s
done
python -m src.evaluation.metrics --bert-score
python -m src.evaluation.statistics
python -m src.evaluation.hallucination_template
python -m src.evaluation.plots

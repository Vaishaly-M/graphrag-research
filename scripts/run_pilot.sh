$ErrorActionPreference = "Stop"

$systems = @(
    "plain_llm",
    "vector_rag",
    "langchain_graphrag",
    "llamaindex_graphrag",
    "fixed_graph_rag",
    "fixed_hybrid_rag",
    "oracle_hybrid_rag",
    "adaptive_hybrid_graphrag"
)

foreach ($system in $systems) {
    Write-Host "========================================"
    Write-Host "Running system: $system"
    Write-Host "========================================"

    python -m "src.systems.$system" --limit 20

    if ($LASTEXITCODE -ne 0) {
        throw "System '$system' failed with exit code $LASTEXITCODE."
    }
}

Write-Host "========================================"
Write-Host "Running evaluation metrics"
Write-Host "========================================"

python -m src.evaluation.metrics

if ($LASTEXITCODE -ne 0) {
    throw "Evaluation failed with exit code $LASTEXITCODE."
}

Write-Host "Pilot evaluation completed successfully."
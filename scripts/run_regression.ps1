$ErrorActionPreference = "Stop"

# Frozen 7-question regression suite (Guide Section 10.2). Every fixed
# pilot failure should get added to data/benchmark/regression_expectations.json
# so it never silently regresses again.

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
    Write-Host "Regression: $system"
    Write-Host "========================================"

    python -m "src.systems.$system" `
        --benchmark-file data/benchmark/benchmark_pilot_7.csv `
        --output-dir results/regression `
        --reset

    if ($LASTEXITCODE -ne 0) {
        throw "System '$system' failed with exit code $LASTEXITCODE."
    }
}

Write-Host "========================================"
Write-Host "Checking regression expectations"
Write-Host "========================================"

python -m src.evaluation.regression_check --results-dir results/regression

if ($LASTEXITCODE -ne 0) {
    throw "Regression check failed -- see results/regression_report.json"
}

Write-Host "Regression suite passed."

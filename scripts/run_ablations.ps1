# WP8 ablation matrix (Guide Section 14). Each variant reuses
# adaptive_hybrid_graphrag.py's own codebase via one CLI flag (see
# AblationConfig in that file), so every variant differs from the full
# system by exactly one mechanism -- never a forked copy.
#
# Run against the dev split by default, NOT hidden-test: ablations are
# for understanding the system during development, and running them
# against hidden-test would itself be a form of tuning on it (Guide
# Section 4.1). Requires data/benchmark/splits/dev.csv to exist already
# (python -m src.benchmark_gen.split_benchmark).

param(
    [string]$BenchmarkFile = "data/benchmark/splits/dev.csv",
    [string]$OutputRoot = "results/ablations"
)

$ErrorActionPreference = "Stop"

$variants = [ordered]@{
    "full_system"         = @()
    "no_vector"           = @("--no-vector")
    "no_graph"            = @("--no-graph")
    "no_routing"          = @("--no-routing")
    "no_templates"        = @("--no-templates")
    "no_fallback"         = @("--no-fallback")
    "no_validation"       = @("--no-validation")
    "fixed_1hop"          = @("--fixed-hops", "1")
    "fixed_2hop"          = @("--fixed-hops", "2")
    "fixed_3hop"          = @("--fixed-hops", "3")
    "fusion_graph_heavy"  = @("--fusion-weights", "0.85,0.10,0.05")
    "fusion_vector_heavy" = @("--fusion-weights", "0.50,0.45,0.05")
    "fusion_equal_weight" = @("--fusion-weights", "0.40,0.40,0.20")
}

foreach ($name in $variants.Keys) {
    $extraArgs = $variants[$name]
    $outputDir = Join-Path $OutputRoot $name

    Write-Host "========================================"
    Write-Host "Ablation: $name"
    Write-Host "========================================"

    python -m src.systems.adaptive_hybrid_graphrag `
        --benchmark-file $BenchmarkFile `
        --output-dir $outputDir `
        --reset `
        @extraArgs

    if ($LASTEXITCODE -ne 0) {
        throw "Ablation '$name' failed with exit code $LASTEXITCODE."
    }
}

Write-Host "========================================"
Write-Host "Evaluating all ablation variants"
Write-Host "========================================"

foreach ($name in $variants.Keys) {
    $inputDir = Join-Path $OutputRoot $name
    $evalDir = Join-Path $inputDir "evaluation"

    python -m src.evaluation.metrics `
        --input-dir $inputDir `
        --benchmark-file $BenchmarkFile `
        --output-dir $evalDir

    if ($LASTEXITCODE -ne 0) {
        throw "Evaluation for ablation '$name' failed with exit code $LASTEXITCODE."
    }
}

Write-Host "Ablation matrix complete."
Write-Host "Per-variant results: $OutputRoot/<variant>/evaluation/summary_metrics.csv"

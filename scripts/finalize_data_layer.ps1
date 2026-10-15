param([Parameter(Mandatory=$true)][int]$IndexProcessId)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (Get-Process -Id $IndexProcessId -ErrorAction SilentlyContinue) {
    Wait-Process -Id $IndexProcessId
}
python -B -m analysis.validate_indexes
if ($LASTEXITCODE -ne 0) { throw 'Index validation failed; Part 1B remains incomplete.' }
python -B -m analysis.report_data_layer
if ($LASTEXITCODE -ne 0) { throw 'Part 1B acceptance report failed.' }
Write-Output 'Part 1B complete. No next phase started.'

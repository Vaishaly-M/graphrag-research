param([Parameter(Mandatory=$true)][int]$GridProcessId)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (Get-Process -Id $GridProcessId -ErrorAction SilentlyContinue) {
    Wait-Process -Id $GridProcessId
}
if (-not (Test-Path -LiteralPath 'configs/vector_selected.yaml')) {
    throw 'Grid did not produce a selected config; inspect runs/vector_tuning/build.stderr.log.'
}
python -B -m analysis.publish_selected_vector
if ($LASTEXITCODE -ne 0) { throw 'Selected index publication failed.' }
Write-Output 'Vector grid and selected index complete. Live Gemini smoke remains pending account access.'

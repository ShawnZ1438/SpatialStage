$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:STAGE_SPATIAL_DATA = Join-Path $PSScriptRoot 'SpatialStage-test-data'
$env:SPATIALSTAGE_DIAGNOSTICS = '0'
Write-Host 'Open http://127.0.0.1:8765. Choose silent simulation or stereo monitor; output starts muted.'
& "$PSScriptRoot\.venv\Scripts\python.exe" -m stagespatialcue.server

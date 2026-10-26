# Windows local simulation console: the real engine with silent output or a
# headphone monitor; nothing reaches a four-channel interface unless chosen.
# -InstallOnly prepares .venv without starting the engine.
param([switch]$InstallOnly)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$health = 'http://127.0.0.1:8765/api/health'
$url = 'http://127.0.0.1:8765/?mode=perform'

function Get-Health {
  try { return Invoke-RestMethod $health -TimeoutSec 1 } catch { return $null }
}

# Another engine on the port: reuse a current one, offer to stop a stale one.
$running = if ($InstallOnly) { $null } else { Get-Health }
if ($running) {
  if ($running.features -contains 'virtual-monitor') {
    Write-Host "SpatialStage is already running. Opening $url"
    Start-Process $url
    exit 0
  }
  $owner = (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess
  $command = if ($owner) { (Get-CimInstance Win32_Process -Filter "ProcessId=$owner").CommandLine } else { 'unknown' }
  Write-Host 'An OLDER SpatialStage engine is using port 8765:' -ForegroundColor Yellow
  Write-Host "  PID $owner  $command"
  Write-Host '  旧版本 SpatialStage 正在占用 8765 端口。'
  $answer = Read-Host 'Stop it and start this version? 停止旧版本并启动当前版本？ [y/N]'
  if ($answer -notmatch '^[yY]') { exit 1 }
  Stop-Process -Id $owner
  Start-Sleep -Seconds 1
}

# First run (or changed dependencies): create .venv with Python 3.11-3.13.
if (-not (Test-Path '.venv\Scripts\python.exe')) {
  $python = $null
  foreach ($candidate in @(@('py', '-3.12'), @('py', '-3.13'), @('py', '-3.11'), @('python'))) {
    $exe, $rest = $candidate
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    & $exe @rest -c 'import sys; assert (3,11) <= sys.version_info[:2] < (3,14)' 2>$null
    if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
  }
  if (-not $python) { throw 'Install Python 3.12 from python.org (or winget install Python.Python.3.12), then run this again.' }
  $exe, $rest = $python
  & $exe @rest -m venv .venv
}
$stamp = (Get-FileHash pyproject.toml -Algorithm SHA256).Hash
$stampFile = '.venv\.spatialstage-install'
if (-not (Test-Path $stampFile) -or (Get-Content $stampFile) -ne $stamp) {
  & '.venv\Scripts\python.exe' -m pip install -e .
  if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed (internet needed on first run).' }
  Set-Content -Path $stampFile -Value $stamp
}
if ($InstallOnly) { Write-Host 'Environment ready.'; exit 0 }

$env:STAGE_SPATIAL_DATA = Join-Path $PSScriptRoot 'SpatialStage-test-data'
$env:SPATIALSTAGE_DIAGNOSTICS = '0'
Write-Host 'SpatialStage simulation at http://127.0.0.1:8765 (opens automatically).'
Write-Host 'Use "Connect silent simulation" or a headphone monitor; output starts muted.'
Write-Host 'Keep this window open; closing it stops the engine. 保持此窗口打开，关闭即停止。'
Start-Job -ArgumentList $health, $url {
  param($health, $url)
  for ($i = 0; $i -lt 120; $i++) {
    try { Invoke-RestMethod $health -TimeoutSec 1 | Out-Null; Start-Process $url; break }
    catch { Start-Sleep -Milliseconds 250 }
  }
} | Out-Null
& '.venv\Scripts\python.exe' -m stagespatialcue.server

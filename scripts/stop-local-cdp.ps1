Param(
  [string]$CdpPort = "9222",
  [string]$ChromeUserDataDir = "",
  [switch]$StopDocker
)

$ErrorActionPreference = "SilentlyContinue"

Write-Host "Stoppe lokalen CDP-Runner ..."
$runnerProcs = Get-CimInstance Win32_Process | Where-Object {
  ($_.Name -match "python|py") -and ($_.CommandLine -match "cdp_runner[\\/]runner\.py")
}
foreach ($proc in $runnerProcs) {
  Stop-Process -Id $proc.ProcessId -Force
}

if (-not $ChromeUserDataDir) {
  $ChromeUserDataDir = Join-Path $env:LOCALAPPDATA "SignalKiosk\cdp-chrome-profile"
}

Write-Host "Stoppe Chrome/Chromium mit CDP-Port $CdpPort ..."
$chromeProcs = Get-CimInstance Win32_Process | Where-Object {
  ($_.Name -match "chrome|chromium") -and (
    ($_.CommandLine -match "--remote-debugging-port=$CdpPort") -or
    ($_.CommandLine -like "*--user-data-dir=$ChromeUserDataDir*")
  )
}
foreach ($proc in $chromeProcs) {
  Stop-Process -Id $proc.ProcessId -Force
}

if ($StopDocker) {
  Write-Host "Stoppe Docker Compose Services ..."
  $root = Split-Path -Parent $PSScriptRoot
  Set-Location $root
  docker compose down
}

Write-Host "Fertig."

Param(
  [Parameter(Mandatory = $true, Position = 0)]
  [ValidateSet("up", "down")]
  [string]$Action,

  [string]$AppBaseUrl = "http://127.0.0.1:8081",
  [string]$ChromeBin = "",
  [string]$CdpPort = "9222",
  [string]$PollIntervalSeconds = "1.5",
  [string]$ChromeUserDataDir = "",
  [string]$HostControlUrl = "http://127.0.0.1:9510",
  [string]$HostControlToken = ""
)

$ErrorActionPreference = "Stop"

$scriptsDir = $PSScriptRoot
$root = Split-Path -Parent $scriptsDir
Set-Location $root

$localCdp = Join-Path $scriptsDir "local-cdp.ps1"
$startHostControl = Join-Path $scriptsDir "start-local-host-control.ps1"
$stopHostControl = Join-Path $scriptsDir "stop-local-host-control.ps1"

if (!(Test-Path $localCdp)) { throw "Missing script: $localCdp" }
if (!(Test-Path $startHostControl)) { throw "Missing script: $startHostControl" }
if (!(Test-Path $stopHostControl)) { throw "Missing script: $stopHostControl" }

if ($Action -eq "up") {
  Write-Host "[1/4] Starting Docker services (app, frontend)"
  docker compose up -d --build app frontend

  Write-Host "[2/4] Stopping containerized cdp-runner profile (if running)"
  cmd /c "docker compose --profile cdp-runner stop cdp-runner >nul 2>nul"

  Write-Host "[3/4] Starting local CDP runner"
  & $localCdp start -AppBaseUrl $AppBaseUrl -ChromeBin $ChromeBin -CdpPort $CdpPort -PollIntervalSeconds $PollIntervalSeconds -ChromeUserDataDir $ChromeUserDataDir

  Write-Host "[4/4] Starting local host control agent"
  if ($HostControlToken) {
    & $startHostControl -HostControlUrl $HostControlUrl -HostControlToken $HostControlToken
  } else {
    & $startHostControl -HostControlUrl $HostControlUrl
  }

  Write-Host ""
  Write-Host "Local dev stack is up."
  Write-Host "- Admin UI: http://127.0.0.1:8080"
  Write-Host "- Backend API: $AppBaseUrl"
  Write-Host "- Host control: $HostControlUrl"
  exit 0
}

Write-Host "[1/3] Stopping local host control agent"
& $stopHostControl

Write-Host "[2/3] Stopping local CDP runner and managed Chrome"
& $localCdp stop -CdpPort $CdpPort -ChromeUserDataDir $ChromeUserDataDir

Write-Host "[3/3] Stopping Docker services"
docker compose stop app frontend

Write-Host ""
Write-Host "Local dev stack is down."

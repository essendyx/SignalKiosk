Param(
  [Parameter(Mandatory = $true, Position = 0)]
  [ValidateSet("start", "stop", "restart")]
  [string]$Action,

  [string]$AppBaseUrl = "http://127.0.0.1:8081",
  [string]$ChromeBin = "",
  [string]$CdpPort = "9222",
  [string]$PollIntervalSeconds = "1.5",
  [string]$ChromeUserDataDir = "",
  [switch]$StopDocker
)

$ErrorActionPreference = "Stop"

$scriptsDir = $PSScriptRoot
$startScript = Join-Path $scriptsDir "start-local-cdp.ps1"
$stopScript = Join-Path $scriptsDir "stop-local-cdp.ps1"

if (!(Test-Path $startScript)) {
  throw "Start-Script nicht gefunden: $startScript"
}
if (!(Test-Path $stopScript)) {
  throw "Stop-Script nicht gefunden: $stopScript"
}

switch ($Action) {
  "start" {
    & $startScript -AppBaseUrl $AppBaseUrl -ChromeBin $ChromeBin -CdpPort $CdpPort -PollIntervalSeconds $PollIntervalSeconds -ChromeUserDataDir $ChromeUserDataDir
    break
  }
  "stop" {
    if ($StopDocker) {
      & $stopScript -CdpPort $CdpPort -ChromeUserDataDir $ChromeUserDataDir -StopDocker
    } else {
      & $stopScript -CdpPort $CdpPort -ChromeUserDataDir $ChromeUserDataDir
    }
    break
  }
  "restart" {
    if ($StopDocker) {
      & $stopScript -CdpPort $CdpPort -ChromeUserDataDir $ChromeUserDataDir -StopDocker
    } else {
      & $stopScript -CdpPort $CdpPort -ChromeUserDataDir $ChromeUserDataDir
    }
    Start-Sleep -Seconds 1
    & $startScript -AppBaseUrl $AppBaseUrl -ChromeBin $ChromeBin -CdpPort $CdpPort -PollIntervalSeconds $PollIntervalSeconds -ChromeUserDataDir $ChromeUserDataDir
    break
  }
}

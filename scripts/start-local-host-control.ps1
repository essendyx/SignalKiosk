Param(
  [string]$HostControlUrl = "http://127.0.0.1:9510",
  [string]$HostControlToken = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $HostControlToken) {
  $envFile = Join-Path $root ".env"
  if (Test-Path $envFile) {
    $line = Select-String -Path $envFile -Pattern '^HOST_CONTROL_TOKEN=' | Select-Object -First 1
    if ($line) {
      $HostControlToken = ($line.Line -split '=', 2)[1].Trim()
    }
  }
}

if (-not $HostControlToken) {
  throw "HOST_CONTROL_TOKEN fehlt. In .env setzen oder -HostControlToken uebergeben."
}

$uri = [Uri]$HostControlUrl
$bind = $uri.Host
$port = [string]$uri.Port

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "python"
$psi.Arguments = "`"$root\scripts\host-control-agent.py`""
$psi.WorkingDirectory = $root
$psi.UseShellExecute = $false
$psi.EnvironmentVariables["PROJECT_DIR"] = $root
$psi.EnvironmentVariables["HOST_CONTROL_BIND"] = $bind
$psi.EnvironmentVariables["HOST_CONTROL_PORT"] = $port
$psi.EnvironmentVariables["HOST_CONTROL_TOKEN"] = $HostControlToken
$psi.EnvironmentVariables["LOCAL_CDP_WRAPPER"] = "$root\scripts\local-cdp.ps1"

[System.Diagnostics.Process]::Start($psi) | Out-Null
Write-Host "Host control agent gestartet auf $HostControlUrl"

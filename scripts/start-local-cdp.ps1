Param(
  [string]$AppBaseUrl = "http://127.0.0.1:8081",
  [string]$ChromeBin = "",
  [string]$CdpPort = "9222",
  [string]$PollIntervalSeconds = "1.5",
  [string]$ChromeUserDataDir = ""
)

$ErrorActionPreference = "Stop"

function Resolve-ChromePath {
  param([string]$Candidate)
  if ($Candidate -and (Test-Path $Candidate)) {
    return $Candidate
  }

  $paths = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "C:\Program Files\Chromium\Application\chrome.exe",
    "C:\Program Files (x86)\Chromium\Application\chrome.exe"
  )

  foreach ($path in $paths) {
    if (Test-Path $path) {
      return $path
    }
  }

  throw "Kein Chrome/Chromium gefunden. Uebergib -ChromeBin 'C:\...\chrome.exe'."
}

function Get-PythonCmd {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    return "py"
  }
  if (Get-Command python -ErrorAction SilentlyContinue) {
    return "python"
  }
  throw "Python wurde nicht gefunden. Bitte Python 3 installieren."
}

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$resolvedChrome = Resolve-ChromePath -Candidate $ChromeBin
$pythonCmd = Get-PythonCmd
if (-not $ChromeUserDataDir) {
  $ChromeUserDataDir = Join-Path $env:LOCALAPPDATA "SignalKiosk\cdp-chrome-profile"
}
New-Item -ItemType Directory -Path $ChromeUserDataDir -Force | Out-Null

Write-Host "[1/4] Starte Docker Services (app, frontend) ..."
docker compose up -d --build app frontend

Write-Host "[2/4] Stoppe ggf. containerisierten cdp-runner ..."
cmd /c "docker compose --profile cdp-runner stop cdp-runner >nul 2>nul"

Write-Host "[2b/4] Stoppe ggf. laufenden lokalen CDP-Runner ..."
$localStopScript = Join-Path $PSScriptRoot "stop-local-cdp.ps1"
if (Test-Path $localStopScript) {
  & $localStopScript -CdpPort $CdpPort -ChromeUserDataDir $ChromeUserDataDir
}

Write-Host "[3/4] Installiere Runner-Abhaengigkeiten lokal ..."
if ($pythonCmd -eq "py") {
  py -m pip install -r "cdp_runner\requirements.txt"
} else {
  python -m pip install -r "cdp_runner\requirements.txt"
}

Write-Host "[4/4] Starte lokalen CDP-Runner ..."
$runnerEnv = @{
  APP_BASE_URL = $AppBaseUrl
  CHROME_BIN = $resolvedChrome
  CDP_PORT = $CdpPort
  POLL_INTERVAL_SECONDS = $PollIntervalSeconds
  CHROME_HEADLESS = "false"
  CHROME_USER_DATA_DIR = $ChromeUserDataDir
}

$runnerScript = Join-Path $root "cdp_runner\runner.py"

$envPrefix = $runnerEnv.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }
Write-Host "Runner ENV: $($envPrefix -join ', ')"

$pythonExec = if ($pythonCmd -eq "py") { "py" } else { "python" }
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $pythonExec
$psi.Arguments = "`"$runnerScript`""
$psi.WorkingDirectory = $root
$psi.UseShellExecute = $false
$psi.EnvironmentVariables["APP_BASE_URL"] = $runnerEnv.APP_BASE_URL
$psi.EnvironmentVariables["CHROME_BIN"] = $runnerEnv.CHROME_BIN
$psi.EnvironmentVariables["CDP_PORT"] = $runnerEnv.CDP_PORT
$psi.EnvironmentVariables["POLL_INTERVAL_SECONDS"] = $runnerEnv.POLL_INTERVAL_SECONDS
$psi.EnvironmentVariables["CHROME_HEADLESS"] = $runnerEnv.CHROME_HEADLESS
$psi.EnvironmentVariables["CHROME_USER_DATA_DIR"] = $runnerEnv.CHROME_USER_DATA_DIR

[System.Diagnostics.Process]::Start($psi) | Out-Null

Write-Host ""
Write-Host "Fertig."
Write-Host "- Admin UI: http://127.0.0.1:8080"
Write-Host "- Backend API: $AppBaseUrl"
Write-Host "- Lokaler Chrome sollte jetzt vom Runner gesteuert werden."

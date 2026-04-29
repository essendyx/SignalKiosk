$ErrorActionPreference = "SilentlyContinue"

$procs = Get-CimInstance Win32_Process | Where-Object {
  ($_.Name -match "python|py") -and ($_.CommandLine -match "scripts[\\/]host-control-agent\.py")
}

foreach ($proc in $procs) {
  Stop-Process -Id $proc.ProcessId -Force
}

Write-Host "Host control agent gestoppt."

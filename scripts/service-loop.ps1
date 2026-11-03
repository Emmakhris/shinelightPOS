# Keeps the POS server running: started at Windows start-up by install-service.ps1.
# If the server ever stops (crash, update), it is started again after a few seconds.
param([int]$Port = 8000)
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$python = Join-Path $backend ".venv\Scripts\python.exe"
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir "service.log"

Set-Location $backend
while ($true) {
    Add-Content -Path $log -Value "$(Get-Date -Format s) starting server on port $Port"
    & $python (Join-Path $backend "serve.py") $Port *>> (Join-Path $logDir "server-console.log")
    Add-Content -Path $log -Value "$(Get-Date -Format s) server stopped (exit code $LASTEXITCODE); restarting in 5 seconds"
    Start-Sleep -Seconds 5
}

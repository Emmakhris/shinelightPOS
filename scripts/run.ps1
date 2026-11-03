# Start ShineLight POS in this window (for trying it out). For everyday use, install it with
# scripts\install-service.ps1 so it starts by itself with Windows.
param([int]$Port = 8000)
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"
Assert-Installed

if (Wait-PosHealthy -Port $Port -Seconds 1) {
    Write-Host "ShineLight POS is already running (probably installed as a start-up task)." -ForegroundColor Yellow
    Show-PosAddresses -Port $Port
    exit 0
}

Write-Host "ShineLight POS is starting." -ForegroundColor Green
Show-PosAddresses -Port $Port
Write-Host "Keep this window open. Press Ctrl+C to stop."
Set-Location $Backend
& $Python serve.py $Port

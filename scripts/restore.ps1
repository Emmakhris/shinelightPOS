# Put the POS back to an earlier backup.
#     .\scripts\restore.ps1                     lists the backups
#     .\scripts\restore.ps1 2026-11-03_213000_daily
# Everything entered after that backup is replaced. The current data is saved first as a
# "before-restore" backup, so a restore can itself be undone.
param([string]$Name, [int]$Port = 8000)
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"
Assert-Installed
Set-Location $Backend

if (-not $Name) {
    Write-Host "Backups (newest first):" -ForegroundColor Cyan
    & $Python manage.py restore_backup
    Write-Host ""
    Write-Host "Restore one with:  .\scripts\restore.ps1 <name>"
    exit 0
}

$serviceInstalled = [bool](Get-ScheduledTask -TaskName $ServerTask -ErrorAction SilentlyContinue)
if ($serviceInstalled) { Assert-Admin }

Write-Warning "This replaces ALL current sales, stock and settings with the backup '$Name'."
$answer = Read-Host "Type RESTORE to continue"
if ($answer -ne "RESTORE") { Write-Host "Cancelled."; exit 1 }

Write-Host "Stopping the POS..." -ForegroundColor Cyan
Stop-PosServer

& $Python manage.py restore_backup $Name --yes
$ok = $LASTEXITCODE -eq 0

if ($serviceInstalled) {
    Start-ScheduledTask -TaskName $ServerTask
    if (Wait-PosHealthy -Port $Port) { Write-Host "The POS is running again." -ForegroundColor Green }
} else {
    Write-Host "Start the POS again with scripts\run.ps1"
}
if (-not $ok) { exit 1 }

# Make ShineLight POS start with Windows, restart itself if it stops, and back up every evening.
# Run once in PowerShell **as Administrator**, after scripts\setup.ps1:
#     .\scripts\install-service.ps1                 (port 8000, backup at 21:30)
#     .\scripts\install-service.ps1 -Port 8080 -BackupTime 22:00
param([int]$Port = 8000, [string]$BackupTime = "21:30")
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"
Assert-Admin
Assert-Installed
if (-not (Test-Path (Join-Path $Root "frontend\dist\index.html"))) { throw "The app is not built. Run scripts\setup.ps1 first." }

$loop = Join-Path $PSScriptRoot "service-loop.ps1"
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# 1. The server: starts at boot, before anyone logs in, and never times out.
Write-Host "Registering start-up task..." -ForegroundColor Cyan
$serverAction = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$loop`" -Port $Port" `
    -WorkingDirectory $Backend
$serverSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $ServerTask -Action $serverAction -Trigger (New-ScheduledTaskTrigger -AtStartup) `
    -Settings $serverSettings -Principal $principal -Force `
    -Description "Runs the ShineLight POS server for the tills on this network." | Out-Null

# 2. The nightly backup. StartWhenAvailable runs it later if the PC was off at backup time.
Write-Host "Registering daily backup at $BackupTime..." -ForegroundColor Cyan
$backupAction = New-ScheduledTaskAction -Execute $Python -Argument "`"$Backend\manage.py`" backup --label daily" `
    -WorkingDirectory $Backend
$backupSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName $BackupTask -Action $backupAction -Trigger (New-ScheduledTaskTrigger -Daily -At $BackupTime) `
    -Settings $backupSettings -Principal $principal -Force `
    -Description "Backs up the ShineLight POS database and product images." | Out-Null

# 3. Let tills and tablets on the shop network reach the server (private networks only).
if (-not (Get-NetFirewallRule -DisplayName $FirewallRule -ErrorAction SilentlyContinue)) {
    Write-Host "Opening port $Port in Windows Firewall (private networks)..." -ForegroundColor Cyan
    New-NetFirewallRule -DisplayName $FirewallRule -Direction Inbound -Protocol TCP -LocalPort $Port `
        -Action Allow -Profile Private, Domain | Out-Null
}
$public = Get-NetConnectionProfile -ErrorAction SilentlyContinue | Where-Object { $_.NetworkCategory -eq "Public" }
if ($public) {
    Write-Warning ("This computer's network '" + ($public.Name -join ", ") + "' is set to Public, so tablets cannot connect. " +
        "In Windows Settings > Network, set the shop network to Private.")
}

# 4. Start it now (replacing any copy already running).
Stop-PosServer
Start-ScheduledTask -TaskName $ServerTask
Write-Host "Starting the POS..." -ForegroundColor Cyan
if (Wait-PosHealthy -Port $Port) {
    Write-Host ""
    Write-Host "ShineLight POS is installed and running. It will start by itself whenever this computer starts." -ForegroundColor Green
    Show-PosAddresses -Port $Port
    Write-Host "Logs: $Root\logs    Backups: $Root\backups"
} else {
    Write-Warning "The POS did not answer within a minute. Check $Root\logs\server.log and logs\server-console.log."
}

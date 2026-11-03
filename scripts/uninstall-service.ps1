# Stop ShineLight POS from starting with Windows and remove its firewall rule.
# Your data, backups and logs are not touched. Run as Administrator.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"
Assert-Admin

Stop-PosServer
foreach ($task in @($ServerTask, $BackupTask)) {
    if (Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $task -Confirm:$false
        Write-Host "Removed task: $task"
    }
}
if (Get-NetFirewallRule -DisplayName $FirewallRule -ErrorAction SilentlyContinue) {
    Remove-NetFirewallRule -DisplayName $FirewallRule
    Write-Host "Removed firewall rule: $FirewallRule"
}
Write-Host "Done. Start the POS by hand with scripts\run.ps1, or reinstall with scripts\install-service.ps1." -ForegroundColor Green

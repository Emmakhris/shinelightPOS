# Shared helpers for the ShineLight POS scripts. Dot-source it: . "$PSScriptRoot\common.ps1"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
$ServerTask = "ShineLightPOS Server"
$BackupTask = "ShineLightPOS Backup"
$FirewallRule = "ShineLight POS"

function Assert-Admin {
    $identity = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Please run PowerShell as Administrator (right-click PowerShell > Run as administrator)."
    }
}

function Assert-Installed {
    if (-not (Test-Path $Python)) { throw "The POS is not set up yet. Run scripts\setup.ps1 first." }
}

function Stop-PosServer {
    # Stop the start-up task (if installed) and any server process, so nothing writes to the database.
    if (Get-ScheduledTask -TaskName $ServerTask -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $ServerTask -ErrorAction SilentlyContinue
    }
    Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -and ($_.CommandLine -like "*service-loop.ps1*" -or $_.CommandLine -like "*serve.py*") } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

function Wait-PosHealthy([int]$Port, [int]$Seconds = 60) {
    for ($i = 0; $i -lt $Seconds; $i++) {
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:$Port/api/health/" -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Show-PosAddresses([int]$Port) {
    $ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
        Select-Object -ExpandProperty IPAddress
    Write-Host "  On this computer:  http://localhost:$Port"
    foreach ($ip in $ips) { Write-Host "  On tills/tablets:  http://${ip}:$Port" }
}

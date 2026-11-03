# Start ShineLight POS for the shop. Other tills and tablets on the same Wi-Fi/network
# open the address printed below in their browser.
param([int]$Port = 8000)
$ErrorActionPreference = "Stop"
$backend = Join-Path (Split-Path -Parent $PSScriptRoot) "backend"
Set-Location $backend

$ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    Select-Object -ExpandProperty IPAddress

Write-Host "ShineLight POS is running." -ForegroundColor Green
Write-Host "  On this computer:  http://localhost:$Port"
foreach ($ip in $ips) { Write-Host "  On other devices:  http://${ip}:$Port" }
Write-Host "Keep this window open. Press Ctrl+C to stop."

& .\.venv\Scripts\python.exe -m waitress --listen="0.0.0.0:$Port" --threads=8 config.wsgi:application

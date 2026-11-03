# One-time install (or update) of ShineLight POS on this computer.
# Needs Python 3.12+ and Node.js 20+ installed.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

Write-Host "== Backend ==" -ForegroundColor Cyan
Set-Location $backend
if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
& .\.venv\Scripts\pip.exe install -r requirements.txt

if (-not (Test-Path ".env")) {
    # A random secret key per install. DEBUG off for real use.
    $bytes = New-Object byte[] 48
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $secret = [Convert]::ToBase64String($bytes)
    @(
        "SECRET_KEY=$secret",
        "DEBUG=false",
        "ALLOWED_HOSTS=*",
        "# DATABASE_URL=postgres://pos:password@localhost:5432/shinelightpos"
    ) | Set-Content -Encoding utf8 ".env"
    Write-Host "Created backend\.env" -ForegroundColor Green
}

& .\.venv\Scripts\python.exe manage.py migrate
& .\.venv\Scripts\python.exe manage.py collectstatic --noinput | Out-Null

Write-Host "== Frontend ==" -ForegroundColor Cyan
Set-Location $frontend
npm install
npm run build

Set-Location $root
Write-Host ""
Write-Host "Setup complete. Start the POS with:  .\scripts\run.ps1" -ForegroundColor Green

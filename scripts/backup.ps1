# Back up the database and uploaded images into backups\<date-time>\.
# Schedule it daily with Windows Task Scheduler, and copy the backups folder off this computer.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$target = Join-Path $root "backups\$stamp"
New-Item -ItemType Directory -Force $target | Out-Null

# Read DATABASE_URL from the environment or backend\.env
$dbUrl = $env:DATABASE_URL
$envFile = Join-Path $backend ".env"
if (-not $dbUrl -and (Test-Path $envFile)) {
    $line = Get-Content $envFile | Where-Object { $_ -match "^\s*DATABASE_URL\s*=" } | Select-Object -First 1
    if ($line) { $dbUrl = ($line -split "=", 2)[1].Trim() }
}

if ($dbUrl -and $dbUrl.StartsWith("postgres")) {
    pg_dump --dbname="$dbUrl" --format=custom --file="$target\shinelightpos.dump"
    Write-Host "PostgreSQL dump saved."
} else {
    $db = Join-Path $backend "db.sqlite3"
    # Use SQLite's own backup so a sale in progress cannot corrupt the copy.
    & "$backend\.venv\Scripts\python.exe" -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()" $db "$target\db.sqlite3"
    Write-Host "SQLite database copied."
}

$media = Join-Path $backend "media"
if (Test-Path $media) { Compress-Archive -Path "$media\*" -DestinationPath "$target\media.zip" -Force }

Write-Host "Backup written to $target" -ForegroundColor Green

# Back up the database and product images now into backups\<date-time>_manual\.
# install-service.ps1 also schedules this every evening. Copy the backups folder off this
# computer regularly (flash drive or cloud storage).
param([int]$Keep = 30)
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"
Assert-Installed
Set-Location $Backend
& $Python manage.py backup --label manual --keep $Keep
if ($LASTEXITCODE -ne 0) { exit 1 }

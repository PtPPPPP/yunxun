$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
python scripts/check_release.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python backend/main.py

# Run backend lint, format check and tests. Usage: pwsh scripts/check-backend.ps1
# Requires: backend/.venv (python -m venv backend/.venv; pip install -e "backend[dev]") and ffmpeg on PATH.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$py = Join-Path $backend ".venv\Scripts\python.exe"
$env:PATH = [Environment]::GetEnvironmentVariable("PATH", "User") + ";" + [Environment]::GetEnvironmentVariable("PATH", "Machine")
Set-Location $backend

Write-Host "== ruff check"
& $py -m ruff check app tests
$lint = $LASTEXITCODE
Write-Host "== ruff format --check"
& $py -m ruff format --check app tests
$fmt = $LASTEXITCODE
Write-Host "== pytest"
& $py -m pytest -q -p no:cacheprovider
$tests = $LASTEXITCODE

Write-Host "lint=$lint format=$fmt tests=$tests"
if ($lint -ne 0 -or $fmt -ne 0 -or $tests -ne 0) { exit 1 }

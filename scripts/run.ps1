# One command on Windows: create the environment, build the desk and start InventIQ on http://127.0.0.1:8000
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip -q
& .\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
if (-not (Test-Path "web\dist\index.html")) {
    Push-Location web; npm ci --no-audit --no-fund; npm run build; Pop-Location
}
& .\.venv\Scripts\python.exe -m inventiq serve

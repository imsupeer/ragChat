$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

python -m pip install -r requirements-dev.txt
python -m pytest -v

Push-Location frontend
try {
    npm ci
    $env:NEXT_PUBLIC_API_URL = "http://localhost:8000"
    npm run build
} finally {
    Pop-Location
}

python scripts/eval.py --skip-generation --fake-embeddings

Write-Host "All local validation checks passed."

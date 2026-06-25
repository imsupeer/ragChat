$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

python scripts/stop_workspace.py
exit $LASTEXITCODE

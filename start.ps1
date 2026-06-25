param(
    [switch]$CheckOnly,
    [switch]$DryRun,
    [ValidateSet("ollama", "llama_cpp")]
    [string]$Provider = "ollama",
    [switch]$NoStartServer,
    [switch]$DownloadModel,
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [ValidateSet("local_hash", "sentence_transformers")]
    [string]$Embeddings = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$argsList = @()
if ($CheckOnly) { $argsList += "--check-only" }
if ($DryRun) { $argsList += "--dry-run" }
if ($Provider) { $argsList += @("--provider", $Provider) }
if ($NoStartServer) { $argsList += "--no-start-server" }
if ($DownloadModel) { $argsList += "--download-model" }
if ($BackendOnly) { $argsList += "--backend-only" }
if ($FrontendOnly) { $argsList += "--frontend-only" }
if ($Embeddings) { $argsList += @("--embeddings", $Embeddings) }

python scripts/start_workspace.py @argsList
exit $LASTEXITCODE

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    $Python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $Python) {
    Write-Error "Install Python 3.12, or open this repository in WSL2 Ubuntu and run ./scripts/lab.sh."
}
& $Python.Source (Join-Path $Root "scripts\labctl.py") @args
exit $LASTEXITCODE

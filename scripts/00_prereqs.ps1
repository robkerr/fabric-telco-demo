<#
.SYNOPSIS
    Verify/install prerequisites for the Telco Fabric/Foundry demo.
    - checks Azure CLI + login
    - installs the Fabric CLI (fab) via pip if missing
    - creates a Python venv and installs the lightweight data-generation deps
      (everything you need to generate data locally and run the web app)
.DESCRIPTION
    Only lightweight, cross-platform dependencies are installed. The Fabric Data Agent
    and semantic model are created by running Fabric notebooks (they depend on the Fabric
    runtime / .NET and are not created from the local workstation), so no heavy SDKs are
    installed here.
.NOTES
    Idempotent. Safe to re-run.
#>
[CmdletBinding()]
param(
    [switch]$SkipVenv
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'lib\Common.psm1') -Force
$root = Get-RepoRoot

Write-Host '== Checking Python ==' -ForegroundColor Cyan
Assert-Command python 'Install Python 3.10+ from https://www.python.org/downloads/'
$pyver = (python --version)
Write-Host "  $pyver"

Write-Host '== Checking Azure CLI ==' -ForegroundColor Cyan
if (Get-Command az -ErrorAction SilentlyContinue) {
    $acct = az account show 2>$null | ConvertFrom-Json
    if ($acct) { Write-Host "  Signed in as $($acct.user.name) (sub: $($acct.name))" }
    else { Write-Warning "  Azure CLI present but not logged in. Run 'az login' before setup_spn.ps1." }
} else {
    Write-Warning "  Azure CLI not found. Install: https://learn.microsoft.com/cli/azure/install-azure-cli"
}

Write-Host '== Checking Fabric CLI (fab) ==' -ForegroundColor Cyan
if (-not (Get-Command fab -ErrorAction SilentlyContinue)) {
    Write-Host '  Installing ms-fabric-cli via pip...'
    python -m pip install --upgrade pip | Out-Null
    python -m pip install ms-fabric-cli
} else {
    Write-Host "  $(fab --version 2>$null)"
}

if (-not $SkipVenv) {
    Write-Host '== Creating Python venv + installing data-generation deps ==' -ForegroundColor Cyan
    $venv = Join-Path $root '.venv'
    if (-not (Test-Path $venv)) { python -m venv $venv }
    $pip = Join-Path $venv 'Scripts\pip.exe'
    & $pip install --upgrade pip | Out-Null
    $reqGen = Join-Path $root 'data-generation\requirements.txt'
    if (Test-Path $reqGen) { & $pip install -r $reqGen }
    Write-Host "  venv ready at $venv"
}

Write-Host ''
Write-Host 'Prerequisites checked. Next:' -ForegroundColor Green
Write-Host '  1) python ./data-generation/generate.py --customers 1000'
Write-Host '  2) run the web app (app/README.md) for an instant local demo, or'
Write-Host '  3) az login then ./scripts/setup_spn.ps1 to provision Fabric'

<#
.SYNOPSIS
    Verify/install prerequisites for the Telco Fabric/Foundry demo.
    - checks Azure CLI + login
    - installs the Fabric CLI (fab) via pip if missing
    - creates a Python venv and installs the lightweight data-generation deps
      (everything you need to generate data locally and run the web app)
.DESCRIPTION
    By default this installs ONLY the data-generation dependencies. The Fabric Data
    Agent / semantic-model SDKs are heavy (they pull in jupyterlab/ipywidgets) and are
    best run inside a Fabric notebook. Install them locally only with -IncludeFabricSdk.
    On Windows those packages create very long file paths, so long-path support must be
    enabled first (this script checks and tells you how).
.NOTES
    Idempotent. Safe to re-run.
#>
[CmdletBinding()]
param(
    [switch]$SkipVenv,
    [switch]$IncludeFabricSdk
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'lib\Common.psm1') -Force
$root = Get-RepoRoot

function Test-WindowsLongPaths {
    # True if Windows long-path support is enabled (needed for the Fabric SDK deps).
    try {
        $v = Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' `
            -Name 'LongPathsEnabled' -ErrorAction Stop
        return [int]$v.LongPathsEnabled -eq 1
    } catch { return $false }
}

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

    if ($IncludeFabricSdk) {
        Write-Host '== Installing Fabric Data Agent SDK (heavy) ==' -ForegroundColor Cyan
        if (-not (Test-WindowsLongPaths)) {
            Write-Warning @'
  Windows long-path support is NOT enabled. The Fabric Data Agent SDK pulls in
  jupyterlab/ipywidgets whose files exceed the 260-character path limit and pip fails
  with "No such file or directory". Enable long paths once (elevated PowerShell):

      New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
          -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force

  Then restart your shell and re-run with -IncludeFabricSdk. Alternatively, run the
  data-agent / semantic-model steps inside a Fabric notebook (deps preinstalled) and
  skip the local install.
'@
            Write-Host '  Skipping Fabric SDK install (long paths disabled).' -ForegroundColor Yellow
        } else {
            $reqAgent = Join-Path $root 'fabric\data-agent\requirements.txt'
            if (Test-Path $reqAgent) { & $pip install -r $reqAgent }
            Write-Host '  Fabric Data Agent SDK installed.'
        }
    } else {
        Write-Host '  (Skipped Fabric Data Agent / semantic-model SDKs. Add -IncludeFabricSdk to' -ForegroundColor DarkGray
        Write-Host '   install them locally, or run those steps inside a Fabric notebook.)' -ForegroundColor DarkGray
    }
}

Write-Host ''
Write-Host 'Prerequisites checked. Next:' -ForegroundColor Green
Write-Host '  1) python ./data-generation/generate.py --customers 1000'
Write-Host '  2) run the web app (app/README.md) for an instant local demo, or'
Write-Host '  3) az login then ./scripts/setup_spn.ps1 to provision Fabric'

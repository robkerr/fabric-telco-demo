<#
.SYNOPSIS
    Create & publish the Telco Fabric Data Agent (wrapper around create_data_agent.py).

.DESCRIPTION
    Ensures the data-agent Python deps are installed in the repo venv, exports the
    relevant .env values into the process, and runs the SDK-based creation script.
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'lib\Common.psm1') -Force
$root = Get-RepoRoot
Import-DotEnv | Out-Null

$venvPy = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    Write-Host 'Creating venv...' -ForegroundColor Cyan
    python -m venv (Join-Path $root '.venv')
}
Write-Host 'Installing data-agent dependencies...' -ForegroundColor Cyan
# The fabric-data-agent-sdk pulls in jupyterlab/ipywidgets with very long file paths.
# On Windows this needs long-path support enabled or pip fails with a bogus OSError.
$longPaths = $true
try {
    $lp = Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name 'LongPathsEnabled' -ErrorAction Stop
    $longPaths = [int]$lp.LongPathsEnabled -eq 1
} catch { $longPaths = $false }
if (-not $longPaths) {
    Write-Warning @'
Windows long-path support is disabled; installing the Fabric Data Agent SDK will likely fail.
Enable it once (elevated PowerShell), restart your shell, and re-run:

    New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
        -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force

Or run this step inside a Fabric notebook instead (deps are preinstalled there):
    fabric/data-agent/create_data_agent.py
'@
}
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -r (Join-Path $root 'fabric\data-agent\requirements.txt')
if ($LASTEXITCODE -ne 0) {
    throw "Dependency install failed (exit $LASTEXITCODE). If this is a Windows path-length error, enable LongPathsEnabled (see the warning above) or run create_data_agent.py inside a Fabric notebook."
}

Write-Host 'Running data agent creation...' -ForegroundColor Cyan
& $venvPy (Join-Path $root 'fabric\data-agent\create_data_agent.py')
if ($LASTEXITCODE -ne 0) { throw "create_data_agent.py failed with exit code $LASTEXITCODE." }

Import-DotEnv | Out-Null
Write-Host ''
Write-Host 'Data agent created & published.' -ForegroundColor Green
Write-Host "  DATA_AGENT_ARTIFACT_ID = $($env:DATA_AGENT_ARTIFACT_ID)"
Write-Host "  DATA_AGENT_MCP_ENDPOINT = $($env:DATA_AGENT_MCP_ENDPOINT)"
Write-Host 'Next (Phase 2): ./infra/deploy.ps1' -ForegroundColor Green

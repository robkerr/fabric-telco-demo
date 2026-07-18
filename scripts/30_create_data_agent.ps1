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
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -r (Join-Path $root 'fabric\data-agent\requirements.txt')

Write-Host 'Running data agent creation...' -ForegroundColor Cyan
& $venvPy (Join-Path $root 'fabric\data-agent\create_data_agent.py')
if ($LASTEXITCODE -ne 0) { throw "create_data_agent.py failed with exit code $LASTEXITCODE." }

Import-DotEnv | Out-Null
Write-Host ''
Write-Host 'Data agent created & published.' -ForegroundColor Green
Write-Host "  DATA_AGENT_ARTIFACT_ID = $($env:DATA_AGENT_ARTIFACT_ID)"
Write-Host "  DATA_AGENT_MCP_ENDPOINT = $($env:DATA_AGENT_MCP_ENDPOINT)"
Write-Host 'Next (Phase 2): ./infra/deploy.ps1' -ForegroundColor Green

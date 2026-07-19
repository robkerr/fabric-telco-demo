<#
.SYNOPSIS
    Deploy the Telco Foundry agents (wrapper around deploy_agents.py).

.DESCRIPTION
    Installs the Foundry Python deps into the repo venv and runs the agent deployment,
    which creates the three independent journey agents in the Foundry project and wires the
    Fabric Data Agent, Azure AI Search, and (optional) Web IQ tools (best-effort).

.NOTES
    Requires FOUNDRY_PROJECT_ENDPOINT + FOUNDRY_MODEL and the tool connection names
    (FABRIC_CONNECTION_NAME, AI_SEARCH_CONNECTION_NAME) in .env. Create the connections in
    the Foundry portal first.

    IMPORTANT: the Fabric data agent tool uses identity passthrough (OBO) and does NOT support
    service principals. Sign in as a USER with 'az login' (a user who has access to the Fabric
    data agent + its data sources) before running.
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot '..\scripts\lib\Common.psm1') -Force
$root = Get-RepoRoot
Import-DotEnv | Out-Null

$venvPy = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) { python -m venv (Join-Path $root '.venv') }
Write-Host 'Installing Foundry dependencies...' -ForegroundColor Cyan
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -r (Join-Path $root 'foundry\requirements.txt')

Write-Host 'Deploying Foundry agents...' -ForegroundColor Cyan
& $venvPy (Join-Path $root 'foundry\deploy_agents.py')
if ($LASTEXITCODE -ne 0) { throw "deploy_agents.py failed with exit code $LASTEXITCODE." }

Write-Host ''
Write-Host 'Foundry agents deployed. IDs in foundry/agents.generated.json' -ForegroundColor Green
Write-Host 'Next (Phase 4): deploy the web app in app/ and the Teams manifest in teams/.' -ForegroundColor Green

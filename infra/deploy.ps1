<#
.SYNOPSIS
    Deploy the Azure infrastructure (Phase 2) and write outputs back to .env.

.DESCRIPTION
    Creates the resource group (if needed) and deploys infra/main.bicep, then records
    the Foundry project endpoint, AI Search endpoint, Key Vault, and Web App into .env.
#>
[CmdletBinding()]
param(
    [string]$ResourceGroup,
    [string]$Location,
    [switch]$SkipRoleAssignments,
    [switch]$WhatIf
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot '..\scripts\lib\Common.psm1') -Force
$root = Get-RepoRoot
$env = Import-DotEnv
Assert-Command az 'Install the Azure CLI.'

if (-not $ResourceGroup) { $ResourceGroup = $env.AZURE_RESOURCE_GROUP }
if (-not $Location) { $Location = if ($env.AZURE_LOCATION) { $env.AZURE_LOCATION } else { 'eastus2' } }
if (-not $ResourceGroup) { throw 'AZURE_RESOURCE_GROUP not set in .env (or pass -ResourceGroup).' }

if ($env.AZURE_SUBSCRIPTION_ID) { az account set --subscription $env.AZURE_SUBSCRIPTION_ID }

Write-Host "== Ensuring resource group $ResourceGroup ($Location) ==" -ForegroundColor Cyan
az group create --name $ResourceGroup --location $Location --only-show-errors | Out-Null

$bicep = Join-Path $root 'infra\main.bicep'
$params = @("location=$Location")
if ($env.FABRIC_SQL_ENDPOINT) { $params += "fabricSqlEndpoint=$($env.FABRIC_SQL_ENDPOINT)" }
if ($SkipRoleAssignments) { $params += 'deployRoleAssignments=false' }

if ($WhatIf) {
    Write-Host '== what-if ==' -ForegroundColor Cyan
    az deployment group what-if --resource-group $ResourceGroup --template-file $bicep --parameters $params
    return
}

Write-Host '== Deploying main.bicep (this can take several minutes) ==' -ForegroundColor Cyan
$deployName = "telco-ai-$(Get-Date -Format 'yyyyMMddHHmmss')"
$out = az deployment group create --name $deployName --resource-group $ResourceGroup `
    --template-file $bicep --parameters $params --query properties.outputs -o json | ConvertFrom-Json

if (-not $out) { throw 'Deployment returned no outputs.' }

Set-DotEnvValue -Key 'AZURE_RESOURCE_GROUP' -Value $ResourceGroup
Set-DotEnvValue -Key 'FOUNDRY_PROJECT_ENDPOINT' -Value $out.foundryProjectEndpoint.value
Set-DotEnvValue -Key 'AI_SEARCH_ENDPOINT' -Value $out.searchEndpoint.value
Set-DotEnvValue -Key 'KEY_VAULT_NAME' -Value $out.keyVaultName.value
Set-DotEnvValue -Key 'APP_SERVICE_NAME' -Value $out.webAppName.value

Write-Host ''
Write-Host 'Azure infrastructure deployed. Written to .env:' -ForegroundColor Green
Write-Host "  FOUNDRY_PROJECT_ENDPOINT = $($out.foundryProjectEndpoint.value)"
Write-Host "  AI_SEARCH_ENDPOINT       = $($out.searchEndpoint.value)"
Write-Host "  KEY_VAULT_NAME           = $($out.keyVaultName.value)"
Write-Host "  APP_SERVICE_NAME         = $($out.webAppName.value)"
Write-Host "  Web App URL              = $($out.webAppUrl.value)"
Write-Host 'Next (Phase 3): ./foundry/deploy_agents.ps1' -ForegroundColor Green

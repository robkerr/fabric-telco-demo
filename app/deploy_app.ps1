<#
.SYNOPSIS
    Deploy the agent-desktop web app to the App Service created in Phase 2.

.DESCRIPTION
    Zips the app/ folder and deploys it to $APP_SERVICE_NAME, sets the startup command,
    and pushes the relevant app settings (Foundry + Fabric SQL endpoints).
#>
[CmdletBinding()]
param(
    [string]$AppName,
    [string]$ResourceGroup
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot '..\scripts\lib\Common.psm1') -Force
$root = Get-RepoRoot
$env = Import-DotEnv
Assert-Command az 'Install the Azure CLI.'

if (-not $AppName) { $AppName = $env.APP_SERVICE_NAME }
if (-not $ResourceGroup) { $ResourceGroup = $env.AZURE_RESOURCE_GROUP }
if (-not $AppName -or -not $ResourceGroup) { throw 'APP_SERVICE_NAME / AZURE_RESOURCE_GROUP not set (run infra/deploy.ps1).' }

$appDir = Join-Path $root 'app'
$zip = Join-Path $env:TEMP "telco-app-$(Get-Date -Format 'yyyyMMddHHmmss').zip"
Write-Host "Packaging $appDir ..." -ForegroundColor Cyan
$exclude = @('__pycache__', '.venv')
$items = Get-ChildItem $appDir -Recurse | Where-Object { $exclude -notcontains $_.Name -and $_.FullName -notmatch '__pycache__' }
Compress-Archive -Path (Join-Path $appDir '*') -DestinationPath $zip -Force

Write-Host 'Configuring startup command + settings...' -ForegroundColor Cyan
az webapp config set --name $AppName --resource-group $ResourceGroup `
    --startup-file 'python -m uvicorn main:app --host 0.0.0.0 --port 8000' --only-show-errors | Out-Null

$settings = @()
if ($env.FOUNDRY_PROJECT_ENDPOINT) { $settings += "FOUNDRY_PROJECT_ENDPOINT=$($env.FOUNDRY_PROJECT_ENDPOINT)" }
if ($env.FABRIC_SQL_ENDPOINT) { $settings += "FABRIC_SQL_ENDPOINT=$($env.FABRIC_SQL_ENDPOINT)" }
if ($env.FABRIC_LAKEHOUSE_NAME) { $settings += "FABRIC_LAKEHOUSE_NAME=$($env.FABRIC_LAKEHOUSE_NAME)" }
if ($settings.Count) { az webapp config appsettings set --name $AppName --resource-group $ResourceGroup --settings $settings --only-show-errors | Out-Null }

Write-Host 'Deploying...' -ForegroundColor Cyan
az webapp deploy --name $AppName --resource-group $ResourceGroup --src-path $zip --type zip --only-show-errors | Out-Null
Remove-Item $zip -Force

$hostName = az webapp show --name $AppName --resource-group $ResourceGroup --query defaultHostName -o tsv
Write-Host ''
Write-Host "Web app deployed: https://$hostName" -ForegroundColor Green

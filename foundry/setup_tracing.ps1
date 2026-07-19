<#
.SYNOPSIS
    Enable Foundry tracing by provisioning Application Insights and connecting it to the
    Foundry project.

.DESCRIPTION
    Idempotently:
      1. Ensures a workspace-based Application Insights resource (backed by a Log Analytics
         workspace) in the target resource group.
      2. Creates an 'AppInsights' connection on the Foundry project so the portal Tracing tab
         and the Agent Service emit traces to it.
      3. Writes APPLICATIONINSIGHTS_CONNECTION_STRING back to .env for optional client-side
         (web app) OpenTelemetry export.

.NOTES
    Reads from .env: AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP, AZURE_LOCATION,
    FOUNDRY_PROJECT_ENDPOINT. Optional overrides: FOUNDRY_ACCOUNT_NAME, FOUNDRY_PROJECT_NAME,
    APP_INSIGHTS_NAME, LOG_ANALYTICS_WORKSPACE_NAME.

    Requires 'az login'. The signed-in identity needs Contributor (or equivalent) on the RG
    and the Foundry (Cognitive Services) account.
#>
[CmdletBinding()]
param(
    [string]$AppInsightsName,
    [string]$LogAnalyticsName
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot '..\scripts\lib\Common.psm1') -Force
Import-DotEnv | Out-Null
Assert-Command az

$sub = $env:AZURE_SUBSCRIPTION_ID
$rg = $env:AZURE_RESOURCE_GROUP
$loc = if ($env:AZURE_LOCATION) { $env:AZURE_LOCATION } else { 'westus3' }
if (-not $sub -or -not $rg) { throw 'AZURE_SUBSCRIPTION_ID and AZURE_RESOURCE_GROUP must be set in .env.' }

$apiVersion = '2025-06-01'

# --- Resolve Foundry account + project ------------------------------------------------
$project = $env:FOUNDRY_PROJECT_NAME
if (-not $project -and $env:FOUNDRY_PROJECT_ENDPOINT) {
    $project = ($env:FOUNDRY_PROJECT_ENDPOINT.TrimEnd('/') -split '/')[-1]
}
$account = $env:FOUNDRY_ACCOUNT_NAME
if (-not $account) {
    Write-Host 'Discovering Foundry (AIServices) account in resource group...' -ForegroundColor Cyan
    $account = az cognitiveservices account list -g $rg --subscription $sub `
        --query "[?kind=='AIServices'].name | [0]" -o tsv
}
if (-not $account -or -not $project) {
    throw "Could not resolve Foundry account/project. Set FOUNDRY_ACCOUNT_NAME and FOUNDRY_PROJECT_NAME in .env."
}
Write-Host "Foundry account: $account | project: $project" -ForegroundColor DarkGray

# --- Ensure Log Analytics workspace ---------------------------------------------------
az extension add -n application-insights --only-show-errors 2>$null | Out-Null
if (-not $LogAnalyticsName) { $LogAnalyticsName = $env:LOG_ANALYTICS_WORKSPACE_NAME }
if (-not $LogAnalyticsName) {
    $LogAnalyticsName = az monitor log-analytics workspace list -g $rg --subscription $sub `
        --query "[0].name" -o tsv
}
if (-not $LogAnalyticsName) {
    $LogAnalyticsName = "$account-logs"
    Write-Host "Creating Log Analytics workspace $LogAnalyticsName ..." -ForegroundColor Cyan
    az monitor log-analytics workspace create -g $rg -n $LogAnalyticsName -l $loc --subscription $sub -o none
}
$lawId = az monitor log-analytics workspace show -g $rg -n $LogAnalyticsName --subscription $sub --query id -o tsv
Write-Host "Log Analytics workspace: $LogAnalyticsName" -ForegroundColor DarkGray

# --- Ensure Application Insights (workspace-based) -------------------------------------
if (-not $AppInsightsName) { $AppInsightsName = $env:APP_INSIGHTS_NAME }
if (-not $AppInsightsName) { $AppInsightsName = "$account-appi" }
Write-Host "Ensuring Application Insights $AppInsightsName ..." -ForegroundColor Cyan
$appi = az monitor app-insights component create --app $AppInsightsName -l $loc -g $rg `
    --subscription $sub --workspace $lawId --application-type web -o json | ConvertFrom-Json
$appiId = $appi.id
$connStr = $appi.connectionString
Write-Host "Application Insights ready: $AppInsightsName" -ForegroundColor Green

# --- Connect App Insights to the Foundry project --------------------------------------
# A project allows only ONE AppInsights connection. Reuse the existing one's name if present.
$connName = $AppInsightsName
$existing = az rest --method get `
    --url "https://management.azure.com/subscriptions/$sub/resourceGroups/$rg/providers/Microsoft.CognitiveServices/accounts/$account/projects/$project/connections?api-version=$apiVersion" `
    --query "value[?properties.category=='AppInsights'].name | [0]" -o tsv
if ($existing) { $connName = $existing }

$body = @{
    properties = @{
        category      = 'AppInsights'
        target        = $appiId
        authType      = 'ApiKey'
        isSharedToAll = $true
        credentials   = @{ key = $connStr }
        metadata      = @{ ApiType = 'Azure'; ResourceId = $appiId }
    }
} | ConvertTo-Json -Depth 6
$tmp = Join-Path ([IO.Path]::GetTempPath()) "appi_conn_$([guid]::NewGuid().ToString('N')).json"
$body | Set-Content -Path $tmp -Encoding utf8
$connUrl = "https://management.azure.com/subscriptions/$sub/resourceGroups/$rg/providers/Microsoft.CognitiveServices/accounts/$account/projects/$project/connections/$connName`?api-version=$apiVersion"
Write-Host "Creating/updating project AppInsights connection '$connName' ..." -ForegroundColor Cyan
az rest --method put --url $connUrl --body "@$tmp" -o none
$putExit = $LASTEXITCODE
Remove-Item $tmp -ErrorAction SilentlyContinue
if ($putExit -ne 0) { throw "Failed to create the AppInsights project connection (az exit $putExit)." }

# --- Persist connection string for optional client-side tracing -----------------------
Set-DotEnvValue -Key 'APP_INSIGHTS_NAME' -Value $AppInsightsName | Out-Null
Set-DotEnvValue -Key 'APPLICATIONINSIGHTS_CONNECTION_STRING' -Value $connStr | Out-Null

Write-Host ''
Write-Host 'Tracing enabled.' -ForegroundColor Green
Write-Host " - App Insights: $AppInsightsName (workspace-based on $LogAnalyticsName)" -ForegroundColor Green
Write-Host " - Project connection: $connName (category AppInsights)" -ForegroundColor Green
Write-Host ' - Open the Foundry portal > your project > Tracing. Run an agent, then refresh' -ForegroundColor Green
Write-Host '   (traces can take 1-3 minutes to appear).' -ForegroundColor Green

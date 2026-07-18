<#
.SYNOPSIS
    Run the medallion notebooks in order against the Telco Lakehouse.

.DESCRIPTION
    Runs 01 -> 02 -> 03 -> 04 via the Fabric "RunNotebook" job API, attaching the
    Lakehouse as the default lakehouse, and polls each job to completion.

.NOTES
    Requires 10_provision_fabric.ps1 to have run (notebooks imported, FABRIC_LAKEHOUSE_ID set).
#>
[CmdletBinding()]
param(
    [string[]]$Only  # optional subset, e.g. -Only 03_build_silver_gold
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'lib\Common.psm1') -Force
$env = Import-DotEnv

$ws = $env.FABRIC_WORKSPACE_ID
$lakehouseId = $env.FABRIC_LAKEHOUSE_ID
$lhName = if ($env.FABRIC_LAKEHOUSE_NAME) { $env.FABRIC_LAKEHOUSE_NAME } else { 'TelcoLakehouse' }
if (-not $lakehouseId) { throw "FABRIC_LAKEHOUSE_ID not set. Run 10_provision_fabric.ps1 first." }

$token = Get-FabricToken -UseSpn
$order = @('01_setup_lakehouse', '02_load_bronze', '03_build_silver_gold', '04_ml_scores')
if ($Only) { $order = $order | Where-Object { $Only -contains $_ } }

$notebooks = (Invoke-FabricApi -Method GET -Path "/workspaces/$ws/notebooks" -Token $token).value

foreach ($name in $order) {
    $nb = $notebooks | Where-Object { $_.displayName -eq $name } | Select-Object -First 1
    if (-not $nb) { throw "Notebook '$name' not found in workspace. Re-run 10_provision_fabric.ps1." }

    Write-Host "== Running $name ==" -ForegroundColor Cyan
    $body = @{
        executionData = @{
            defaultLakehouse = @{ name = $lhName; id = $lakehouseId; workspaceId = $ws }
        }
    }
    $uri = "$($env.FABRIC_API_BASE)/workspaces/$ws/items/$($nb.id)/jobs/instances?jobType=RunNotebook"
    $resp = Invoke-WebRequest -Method Post -Uri $uri -Headers @{ Authorization = "Bearer $token" } `
        -Body ($body | ConvertTo-Json -Depth 10) -ContentType 'application/json' -UseBasicParsing
    $statusUrl = $resp.Headers['Location']
    if (-not $statusUrl) { throw "No job status URL returned for $name." }

    $deadline = (Get-Date).AddSeconds(1800)
    do {
        Start-Sleep -Seconds 10
        $job = Invoke-RestMethod -Method Get -Uri $statusUrl -Headers @{ Authorization = "Bearer $token" }
        Write-Host "  status: $($job.status)"
        if ((Get-Date) -gt $deadline) { throw "  $name timed out." }
    } while ($job.status -in @('NotStarted', 'InProgress', 'Running'))

    if ($job.status -ne 'Completed') {
        throw "  $name did not complete (status=$($job.status)): $($job.failureReason.message)"
    }
    Write-Host "  $name completed." -ForegroundColor Green
    # refresh token in case of long total runtime
    $token = Get-FabricToken -UseSpn
    $notebooks = (Invoke-FabricApi -Method GET -Path "/workspaces/$ws/notebooks" -Token $token).value
}

Write-Host ''
Write-Host 'Data load complete. Curated tables + customer_360 are built.' -ForegroundColor Green
Write-Host 'Next: ./scripts/verify_customer360.ps1  then  ./scripts/30_create_data_agent.ps1' -ForegroundColor Green

<#
.SYNOPSIS
    Provision a Fabric Eventhouse (KQL database) with the two real-time telco tables and load
    the committed sample data.

.DESCRIPTION
    Using the service principal from .env (or the signed-in az user), this script:
      1. creates (or reuses) an Eventhouse named $EVENTHOUSE_NAME (auto-creates its KQL database)
      2. resolves the KQL database name + queryServiceUri and writes them to .env
      3. creates the OutageEvents and WebSessions tables (idempotent)
      4. ingests data/kql/*.csv via chunked `.ingest inline`
    Run data-generation/generate_realtime.py first to produce the CSVs.

.NOTES
    Idempotent: reuses the Eventhouse by display name and re-creates/clears the tables before
    ingest. Requires FABRIC_WORKSPACE_ID (+ SPN_* from setup_spn.ps1). The signed-in identity
    needs access to the workspace/Eventhouse.
#>
[CmdletBinding()]
param(
    [switch]$SkipIngest,
    [int]$ChunkSize = 5000
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'lib\Common.psm1') -Force
$root = Get-RepoRoot
$env = Import-DotEnv

$ws = $env.FABRIC_WORKSPACE_ID
if (-not $ws -or $ws -eq '00000000-0000-0000-0000-000000000000') { throw 'FABRIC_WORKSPACE_ID not set in .env.' }
$ehName = if ($env.EVENTHOUSE_NAME) { $env.EVENTHOUSE_NAME } else { 'telco_realtime' }

# Table schemas (KQL column defs). Order must match the CSV columns produced by the generator.
$tables = [ordered]@{
    OutageEvents = @(
        'event_id:string', 'customer_id:string', 'account_id:string', 'geo_id:string',
        'event_time:datetime', 'outage_type:string', 'severity:string', 'status:string',
        'affected_service:string', 'duration_minutes:real', 'restored_time:datetime',
        'reported_by_customer:bool')
    WebSessions  = @(
        'session_id:string', 'customer_id:string', 'session_start:datetime', 'session_end:datetime',
        'duration_seconds:real', 'device_type:string', 'browser:string', 'os:string',
        'entry_page:string', 'exit_page:string', 'page_views:long', 'referrer:string',
        'authenticated:bool', 'converted:bool')
    DeviceMetrics = @(
        'device_id:string', 'account_id:string', 'reading_time:datetime', 'is_online:bool',
        'utilization_pct:real', 'downstream_mbps:real', 'upstream_mbps:real', 'latency_ms:real')
}
$csvFor = @{ OutageEvents = 'outage_events.csv'; WebSessions = 'web_sessions.csv'; DeviceMetrics = 'device_metrics.csv' }

$fabricToken = Get-FabricToken -UseSpn

# --- 1. Create or reuse the Eventhouse ---
Write-Host "== Eventhouse '$ehName' ==" -ForegroundColor Cyan
$existing = (Invoke-FabricApi -Method GET -Path "/workspaces/$ws/eventhouses" -Token $fabricToken).value |
    Where-Object { $_.displayName -eq $ehName } | Select-Object -First 1
if ($existing) {
    $ehId = $existing.id
    Write-Host "  Reusing existing Eventhouse (id=$ehId)"
} else {
    Write-Host '  Creating Eventhouse...'
    $created = Invoke-FabricLro -Path "/workspaces/$ws/eventhouses" -Token $fabricToken `
        -Body @{ displayName = $ehName; description = 'Telco demo real-time (KQL) store' }
    $ehId = $created.id
    Write-Host "  Created Eventhouse (id=$ehId)"
}

# --- 2. Resolve the KQL database (name + queryServiceUri) ---
Write-Host '== Resolving KQL database ==' -ForegroundColor Cyan
$db = $null
for ($i = 0; $i -lt 12 -and -not $db; $i++) {
    $dbs = (Invoke-FabricApi -Method GET -Path "/workspaces/$ws/kqlDatabases" -Token $fabricToken).value
    $db = $dbs | Where-Object { $_.properties.parentEventhouseItemId -eq $ehId } | Select-Object -First 1
    if (-not $db) { $db = $dbs | Where-Object { $_.displayName -eq $ehName } | Select-Object -First 1 }
    if (-not $db) { Start-Sleep -Seconds 5 }
}
if (-not $db) { throw "Could not resolve the KQL database for Eventhouse '$ehName'." }
$dbName = if ($db.properties.databaseName) { $db.properties.databaseName } else { $db.displayName }
$queryUri = $db.properties.queryServiceUri
if (-not $queryUri) { throw 'KQL database has no queryServiceUri yet; wait a moment and re-run.' }
Write-Host "  database: $dbName"
Write-Host "  queryUri: $queryUri"
Set-DotEnvValue -Key 'EVENTHOUSE_NAME' -Value $ehName | Out-Null
Set-DotEnvValue -Key 'KQL_DATABASE_NAME' -Value $dbName | Out-Null
Set-DotEnvValue -Key 'KQL_QUERY_URI' -Value $queryUri | Out-Null

$kustoToken = Get-KustoToken -UseSpn -Resource $queryUri

# --- 3. Create/refresh the tables + ingest ---
# When ingesting, drop + recreate so schema changes (e.g. added columns) apply cleanly and the
# CSV column order always matches the table. With -SkipIngest, create-merge non-destructively.
Write-Host '== Creating tables ==' -ForegroundColor Cyan
foreach ($t in $tables.Keys) {
    $cols = ($tables[$t] -join ', ')
    if ($SkipIngest) {
        Invoke-KustoMgmt -QueryUri $queryUri -Database $dbName -Token $kustoToken `
            -Csl ".create-merge table $t ($cols)" | Out-Null
        Write-Host "  ensured table $t"
    } else {
        Invoke-KustoMgmt -QueryUri $queryUri -Database $dbName -Token $kustoToken `
            -Csl ".drop table $t ifexists" | Out-Null
        Invoke-KustoMgmt -QueryUri $queryUri -Database $dbName -Token $kustoToken `
            -Csl ".create table $t ($cols)" | Out-Null
        Write-Host "  (re)created table $t"
    }
}

if ($SkipIngest) { Write-Host 'Skipping ingest (-SkipIngest).' -ForegroundColor Yellow; return }

# --- 4. Ingest the committed CSV data (chunked inline; tables were just recreated empty) ---
Write-Host '== Ingesting data ==' -ForegroundColor Cyan
foreach ($t in $tables.Keys) {
    $csvPath = Join-Path $root "data\kql\$($csvFor[$t])"
    if (-not (Test-Path $csvPath)) {
        Write-Warning "  $csvPath not found - run generate_realtime.py first. Skipping $t."
        continue
    }
    $lines = [System.IO.File]::ReadAllLines($csvPath)
    $data = $lines | Select-Object -Skip 1 | Where-Object { $_ -ne '' }   # drop header + blanks
    $total = $data.Count
    if ($total -eq 0) { Write-Host "  $t : no rows"; continue }

    $ingested = 0
    for ($start = 0; $start -lt $total; $start += $ChunkSize) {
        $end = [Math]::Min($start + $ChunkSize, $total) - 1
        $chunk = $data[$start..$end] -join "`n"
        $csl = ".ingest inline into table $t <|`n$chunk"
        Invoke-KustoMgmt -QueryUri $queryUri -Database $dbName -Token $kustoToken -Csl $csl | Out-Null
        $ingested += ($end - $start + 1)
        Write-Host "  $t : $ingested / $total rows"
    }
}

Write-Host ''
Write-Host "Eventhouse '$ehName' ready. Database '$dbName' has:" -ForegroundColor Green
Write-Host '  DeviceMetrics  (real-time device telemetry -> time-series binding on Device)' -ForegroundColor Green
Write-Host '  OutageEvents / WebSessions' -ForegroundColor Green
Write-Host 'Next: in the Fabric IQ ontology, add a Device entity (static from gold.dim_customer_device)' -ForegroundColor Green
Write-Host '      + account_has_device, then bind DeviceMetrics as time-series on Device. See' -ForegroundColor Green
Write-Host '      fabric/eventhouse/README.md.' -ForegroundColor Green

<#
.SYNOPSIS
    Stream fresh DeviceMetrics readings (real-time demo). Ingests a new telemetry row with a
    now() timestamp every few seconds for one device, so you can ask the ontology agent
    "what's the utilization in the last few minutes?" and see live data arrive.

.EXAMPLE
    ./scripts/stream_device_metrics.ps1 -AccountId ACCT000001 -IntervalSec 5 -Count 30

.NOTES
    Requires the Eventhouse provisioned (30_provision_eventhouse.ps1) and the capacity running.
    Resolves the device from data/csv/dim_customer_device.csv (or pass -DeviceId directly).
#>
[CmdletBinding()]
param(
    [string]$AccountId,
    [string]$DeviceId,
    [int]$IntervalSec = 5,
    [int]$Count = 30,
    [double]$BaseUtil = 55.0
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'lib\Common.psm1') -Force
$root = Get-RepoRoot
$env = Import-DotEnv

$uri = $env.KQL_QUERY_URI
$db = $env.KQL_DATABASE_NAME
if (-not $uri -or -not $db) { throw 'KQL_QUERY_URI / KQL_DATABASE_NAME not set. Run 30_provision_eventhouse.ps1 first.' }

# Resolve the device from the committed device dimension.
if (-not $DeviceId) {
    if (-not $AccountId) { throw 'Pass -AccountId or -DeviceId.' }
    $csv = Join-Path $root 'data\csv\dim_customer_device.csv'
    $row = Import-Csv $csv | Where-Object { $_.account_id -eq $AccountId } | Select-Object -First 1
    if (-not $row) { throw "No device found for account $AccountId in dim_customer_device.csv." }
    $DeviceId = $row.device_id
}
$acct = if ($AccountId) { $AccountId } else {
    (Import-Csv (Join-Path $root 'data\csv\dim_customer_device.csv') |
        Where-Object { $_.device_id -eq $DeviceId } | Select-Object -First 1).account_id
}

$token = Get-KustoToken -UseSpn -Resource $uri
Write-Host "Streaming DeviceMetrics for device $DeviceId (account $acct): $Count readings, every ${IntervalSec}s" -ForegroundColor Cyan

$rng = [System.Random]::new()
$link = 250.0
for ($i = 1; $i -le $Count; $i++) {
    $util = [Math]::Round([Math]::Max(2, [Math]::Min(99, $BaseUtil + ($rng.NextDouble() - 0.5) * 30)), 1)
    $online = ($rng.NextDouble() -gt 0.03)
    if (-not $online) { $util = 0.0 }
    $down = if ($online) { [Math]::Round($link * (0.6 + 0.4 * ($util / 100.0)) * (0.85 + $rng.NextDouble() * 0.15), 1) } else { 0.0 }
    $up = if ($online) { [Math]::Round($down * (0.08 + $rng.NextDouble() * 0.07), 1) } else { 0.0 }
    $lat = if ($online) { [Math]::Round([Math]::Min(250, 12 + $util * 0.6 + ($rng.NextDouble() - 0.5) * 10), 1) } else { 0.0 }
    $ts = (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss')
    $onlineStr = if ($online) { 'true' } else { 'false' }
    $line = "$DeviceId,$acct,$ts,$onlineStr,$util,$down,$up,$lat"
    Invoke-KustoMgmt -QueryUri $uri -Database $db -Token $token `
        -Csl ".ingest inline into table DeviceMetrics <|`n$line" | Out-Null
    Write-Host ("  [{0}/{1}] {2}  util={3}%  online={4}  down={5}Mbps  lat={6}ms" -f `
        $i, $Count, $ts, $util, $online, $down, $lat)
    if ($i -lt $Count) { Start-Sleep -Seconds $IntervalSec }
}
Write-Host "Done. Ask the agent e.g. 'what is the utilization for account $acct in the last 5 minutes?'" -ForegroundColor Green

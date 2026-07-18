<#
.SYNOPSIS
    Verify the Customer 360 "fetch profile" path against the Lakehouse SQL endpoint.

.DESCRIPTION
    Discovers the SQL analytics endpoint connection string from the Fabric API, then
    runs validation queries against customer_360 using an Entra access token (SPN).
    This mirrors what the Web App does on contact start.
#>
[CmdletBinding()]
param(
    [string]$CustomerId  # optional: fetch one customer's 360 profile
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'lib\Common.psm1') -Force
$env = Import-DotEnv

$ws = $env.FABRIC_WORKSPACE_ID
$lakehouseId = $env.FABRIC_LAKEHOUSE_ID
$lhName = if ($env.FABRIC_LAKEHOUSE_NAME) { $env.FABRIC_LAKEHOUSE_NAME } else { 'TelcoLakehouse' }
if (-not $lakehouseId) { throw "FABRIC_LAKEHOUSE_ID not set. Run the provisioning + load scripts first." }

# --- Discover the SQL analytics endpoint ---
$token = Get-FabricToken -UseSpn
$lh = Invoke-FabricApi -Method GET -Path "/workspaces/$ws/lakehouses/$lakehouseId" -Token $token
$server = $lh.properties.sqlEndpointProperties.connectionString
if (-not $server) { throw "SQL endpoint not ready yet. Wait a minute after loading and retry." }
Write-Host "SQL endpoint: $server" -ForegroundColor Cyan
Write-Host "Database:     $lhName" -ForegroundColor Cyan

# --- Get a SQL access token (Entra) ---
$sqlResource = 'https://database.windows.net'
if ($env.SPN_APP_ID -and $env.SPN_CLIENT_SECRET) {
    $body = @{ client_id = $env.SPN_APP_ID; client_secret = $env.SPN_CLIENT_SECRET
               grant_type = 'client_credentials'; scope = "$sqlResource/.default" }
    $sqlToken = (Invoke-RestMethod -Method Post -ContentType 'application/x-www-form-urlencoded' `
        -Uri "https://login.microsoftonline.com/$($env.SPN_TENANT_ID)/oauth2/v2.0/token" -Body $body).access_token
} else {
    $sqlToken = az account get-access-token --resource $sqlResource --query accessToken -o tsv
}

function Invoke-Query([string]$sql) {
    $conn = New-Object System.Data.SqlClient.SqlConnection
    $conn.ConnectionString = "Server=$server;Database=$lhName;Encrypt=True;TrustServerCertificate=False;"
    $conn.AccessToken = $sqlToken
    $conn.Open()
    try {
        $cmd = $conn.CreateCommand(); $cmd.CommandText = $sql
        $adapter = New-Object System.Data.SqlClient.SqlDataAdapter $cmd
        $ds = New-Object System.Data.DataSet
        [void]$adapter.Fill($ds)
        return $ds.Tables[0]
    } finally { $conn.Close() }
}

Write-Host "`n== customer_360 row count ==" -ForegroundColor Cyan
(Invoke-Query "SELECT COUNT(*) AS customers FROM customer_360") | Format-Table -AutoSize

Write-Host "== New customers with an unpaid first bill (first-bill journey) ==" -ForegroundColor Cyan
(Invoke-Query @"
SELECT TOP 10 customer_id, first_name, last_name, account_status,
       last_invoice_amount, open_balance, risk_band, top_crosssell_product
FROM customer_360
WHERE last_invoice_is_first_bill = 1 AND last_invoice_paid = 0
"@) | Format-Table -AutoSize

Write-Host "== High churn-risk active customers (retention journey) ==" -ForegroundColor Cyan
(Invoke-Query @"
SELECT TOP 10 customer_id, first_name, last_name, churn_probability, churn_top_reason,
       recent_outage_exposure
FROM customer_360
WHERE risk_band = 'High' AND account_status = 'active'
ORDER BY churn_probability DESC
"@) | Format-Table -AutoSize

if ($CustomerId) {
    Write-Host "== Full 360 profile for $CustomerId ==" -ForegroundColor Cyan
    (Invoke-Query "SELECT * FROM customer_360 WHERE customer_id = '$CustomerId'") | Format-List
}

Write-Host "`nCustomer 360 fetch path verified." -ForegroundColor Green

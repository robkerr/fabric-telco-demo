<#
.SYNOPSIS
    Shared helpers for the Telco Fabric/Foundry demo scripts:
    - .env loading / saving
    - Azure + Fabric access-token acquisition
    - Thin Fabric REST wrappers
#>

$script:RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

function Get-RepoRoot { return $script:RepoRoot }

function Get-DotEnvPath {
    return (Join-Path (Get-RepoRoot) '.env')
}

function Import-DotEnv {
    <# Loads .env into a hashtable AND into process env vars. #>
    [CmdletBinding()]
    param([string]$Path = (Get-DotEnvPath))

    $map = @{}
    if (-not (Test-Path $Path)) {
        Write-Warning ".env not found at $Path. Copy .env.example to .env and fill it in."
        return $map
    }
    foreach ($line in Get-Content -Path $Path) {
        $trimmed = $line.Trim()
        if ($trimmed -eq '' -or $trimmed.StartsWith('#')) { continue }
        $idx = $trimmed.IndexOf('=')
        if ($idx -lt 1) { continue }
        $key = $trimmed.Substring(0, $idx).Trim()
        $val = $trimmed.Substring($idx + 1).Trim().Trim('"')
        $map[$key] = $val
        Set-Item -Path "Env:$key" -Value $val
    }
    return $map
}

function Set-DotEnvValue {
    <# Upserts a key=value into .env (creates the file from nothing if needed). #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Key,
        [Parameter(Mandatory)][AllowEmptyString()][string]$Value,
        [string]$Path = (Get-DotEnvPath)
    )
    if (-not (Test-Path $Path)) { New-Item -ItemType File -Path $Path -Force | Out-Null }
    $lines = @(Get-Content -Path $Path -ErrorAction SilentlyContinue)
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^\s*$([regex]::Escape($Key))\s*=") {
            $lines[$i] = "$Key=$Value"
            $found = $true
            break
        }
    }
    if (-not $found) { $lines += "$Key=$Value" }
    Set-Content -Path $Path -Value $lines
    Set-Item -Path "Env:$Key" -Value $Value
}

function Assert-Command {
    param([Parameter(Mandatory)][string]$Name, [string]$Hint)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' not found. $Hint"
    }
}

function Get-FabricToken {
    <#
      Returns a bearer token for the Fabric API.
      Uses the SPN from .env when present, otherwise falls back to the signed-in az user.
      Fabric API audience: https://api.fabric.microsoft.com
    #>
    [CmdletBinding()]
    param([switch]$UseSpn)

    $env = Import-DotEnv
    $resource = 'https://api.fabric.microsoft.com'

    if ($UseSpn -or ($env.SPN_APP_ID -and $env.SPN_CLIENT_SECRET)) {
        if (-not ($env.SPN_APP_ID -and $env.SPN_CLIENT_SECRET -and $env.SPN_TENANT_ID)) {
            throw "SPN requested but SPN_APP_ID/SPN_CLIENT_SECRET/SPN_TENANT_ID are not all set in .env. Run setup_spn.ps1."
        }
        $body = @{
            client_id     = $env.SPN_APP_ID
            client_secret = $env.SPN_CLIENT_SECRET
            grant_type    = 'client_credentials'
            scope         = "$resource/.default"
        }
        $tokenUri = "https://login.microsoftonline.com/$($env.SPN_TENANT_ID)/oauth2/v2.0/token"
        $resp = Invoke-RestMethod -Method Post -Uri $tokenUri -Body $body -ContentType 'application/x-www-form-urlencoded'
        return $resp.access_token
    }

    Assert-Command az 'Install the Azure CLI: https://learn.microsoft.com/cli/azure/'
    $token = az account get-access-token --resource $resource --query accessToken -o tsv
    if (-not $token) { throw "Failed to obtain a Fabric token via 'az account get-access-token'." }
    return $token
}

function Invoke-FabricApi {
    <# Thin wrapper over the Fabric REST API with auth + JSON handling. #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidateSet('GET','POST','PATCH','PUT','DELETE')][string]$Method,
        [Parameter(Mandatory)][string]$Path,   # e.g. /workspaces/{id}/items
        [object]$Body,
        [string]$Token,
        [switch]$UseSpn
    )
    $env = Import-DotEnv
    $base = if ($env.FABRIC_API_BASE) { $env.FABRIC_API_BASE } else { 'https://api.fabric.microsoft.com/v1' }
    if (-not $Token) { $Token = Get-FabricToken -UseSpn:$UseSpn }

    $uri = if ($Path.StartsWith('http')) { $Path } else { "$base$Path" }
    $headers = @{ Authorization = "Bearer $Token" }
    $params = @{ Method = $Method; Uri = $uri; Headers = $headers }
    if ($null -ne $Body) {
        $params.Body = ($Body | ConvertTo-Json -Depth 20)
        $params.ContentType = 'application/json'
    }
    return Invoke-RestMethod @params
}

function Get-StorageToken {
    <# Token for the OneLake DFS (ADLS Gen2) endpoint. Prefers SPN, else az user. #>
    [CmdletBinding()]
    param([switch]$UseSpn)
    $env = Import-DotEnv
    $resource = 'https://storage.azure.com'
    if ($UseSpn -or ($env.SPN_APP_ID -and $env.SPN_CLIENT_SECRET)) {
        $body = @{
            client_id     = $env.SPN_APP_ID
            client_secret = $env.SPN_CLIENT_SECRET
            grant_type    = 'client_credentials'
            scope         = "$resource/.default"
        }
        $tokenUri = "https://login.microsoftonline.com/$($env.SPN_TENANT_ID)/oauth2/v2.0/token"
        return (Invoke-RestMethod -Method Post -Uri $tokenUri -Body $body `
                -ContentType 'application/x-www-form-urlencoded').access_token
    }
    Assert-Command az 'Install the Azure CLI.'
    return (az account get-access-token --resource $resource --query accessToken -o tsv)
}

function Send-OneLakeFile {
    <#
      Uploads a local file to OneLake via the ADLS Gen2 DFS API
      (create -> append -> flush). Good for the small demo parquet files.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$WorkspaceId,
        [Parameter(Mandatory)][string]$LakehouseId,
        [Parameter(Mandatory)][string]$RelativePath,   # e.g. Files/landing/dim_customer.parquet
        [Parameter(Mandatory)][string]$LocalPath,
        [string]$Token
    )
    if (-not $Token) { $Token = Get-StorageToken }
    $base = "https://onelake.dfs.fabric.microsoft.com/$WorkspaceId/$LakehouseId/$RelativePath"
    $headers = @{ Authorization = "Bearer $Token"; 'x-ms-version' = '2021-08-06' }
    $bytes = [System.IO.File]::ReadAllBytes($LocalPath)

    Invoke-WebRequest -Method Put -Uri "$($base)?resource=file" -Headers $headers `
        -ContentType 'application/octet-stream' -UseBasicParsing | Out-Null
    Invoke-WebRequest -Method Patch -Uri "$($base)?action=append&position=0" -Headers $headers `
        -Body $bytes -ContentType 'application/octet-stream' -UseBasicParsing | Out-Null
    Invoke-WebRequest -Method Patch -Uri "$($base)?action=flush&position=$($bytes.Length)" `
        -Headers $headers -UseBasicParsing | Out-Null
}

function Invoke-FabricLro {
    <#
      POST that may return a 202 long-running operation. Polls the Operation-Location
      / Location header until the operation succeeds, then returns the final response.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Path,
        [object]$Body,
        [string]$Token,
        [int]$TimeoutSec = 600
    )
    $env = Import-DotEnv
    $base = if ($env.FABRIC_API_BASE) { $env.FABRIC_API_BASE } else { 'https://api.fabric.microsoft.com/v1' }
    if (-not $Token) { $Token = Get-FabricToken }
    $uri = if ($Path.StartsWith('http')) { $Path } else { "$base$Path" }
    $headers = @{ Authorization = "Bearer $Token" }

    $resp = Invoke-WebRequest -Method Post -Uri $uri -Headers $headers `
        -Body ($Body | ConvertTo-Json -Depth 30) -ContentType 'application/json' -UseBasicParsing
    if ($resp.StatusCode -eq 201 -or $resp.StatusCode -eq 200) {
        return ($resp.Content | ConvertFrom-Json)
    }
    # PowerShell 7 returns header values as string[]; take the first element.
    $opUrl = @($resp.Headers['Operation-Location'])[0]
    if (-not $opUrl) { $opUrl = @($resp.Headers['Location'])[0] }
    if (-not $opUrl) { return ($resp.Content | ConvertFrom-Json) }

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
        $op = Invoke-RestMethod -Method Get -Uri $opUrl -Headers $headers
        if ($op.status -in @('Succeeded', 'Completed')) {
            try { return (Invoke-RestMethod -Method Get -Uri "$opUrl/result" -Headers $headers) }
            catch { return $op }
        }
        if ($op.status -in @('Failed', 'Cancelled')) {
            throw "Long-running operation $($op.status): $($op.error.message)"
        }
    }
    throw "Long-running operation timed out after $TimeoutSec s."
}

function Get-KustoToken {
    <#
      Returns a bearer token for a Fabric Eventhouse (Kusto) data plane. The audience must be
      the cluster's own URI (queryServiceUri), e.g. https://<id>.kusto.fabric.microsoft.com.
      SPN from .env, else signed-in az user.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Resource,   # the cluster/queryService URI
        [switch]$UseSpn
    )
    $env = Import-DotEnv
    $res = $Resource.TrimEnd('/')
    if ($UseSpn -or ($env.SPN_APP_ID -and $env.SPN_CLIENT_SECRET)) {
        if (-not ($env.SPN_APP_ID -and $env.SPN_CLIENT_SECRET -and $env.SPN_TENANT_ID)) {
            throw "SPN requested but SPN_APP_ID/SPN_CLIENT_SECRET/SPN_TENANT_ID are not all set in .env. Run setup_spn.ps1."
        }
        $body = @{
            client_id     = $env.SPN_APP_ID
            client_secret = $env.SPN_CLIENT_SECRET
            grant_type    = 'client_credentials'
            scope         = "$res/.default"
        }
        $tokenUri = "https://login.microsoftonline.com/$($env.SPN_TENANT_ID)/oauth2/v2.0/token"
        return (Invoke-RestMethod -Method Post -Uri $tokenUri -Body $body `
                -ContentType 'application/x-www-form-urlencoded').access_token
    }
    Assert-Command az 'Install the Azure CLI.'
    $token = az account get-access-token --resource $res --query accessToken -o tsv
    if (-not $token) { throw "Failed to obtain a Kusto token via 'az account get-access-token'." }
    return $token
}

function Invoke-KustoMgmt {
    <#
      Runs a Kusto management/query command against a Fabric Eventhouse KQL database via the
      REST endpoint {queryUri}/v1/rest/mgmt. Returns the parsed response. Use for
      .create/.drop/.ingest/.show commands. For queries pass -Query to hit /v1/rest/query.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$QueryUri,   # queryServiceUri, e.g. https://<guid>.kusto.fabric.microsoft.com
        [Parameter(Mandatory)][string]$Database,
        [Parameter(Mandatory)][string]$Csl,        # the command/query text
        [string]$Token,
        [switch]$Query,                            # hit /v1/rest/query instead of /v1/rest/mgmt
        [int]$TimeoutSec = 300
    )
    if (-not $Token) { $Token = Get-KustoToken }
    $leaf = if ($Query) { 'query' } else { 'mgmt' }
    $uri = "$($QueryUri.TrimEnd('/'))/v1/rest/$leaf"
    $headers = @{ Authorization = "Bearer $Token"; Accept = 'application/json' }
    $payload = @{ db = $Database; csl = $Csl } | ConvertTo-Json -Depth 4
    return Invoke-RestMethod -Method Post -Uri $uri -Headers $headers `
        -Body $payload -ContentType 'application/json' -TimeoutSec $TimeoutSec
}

Export-ModuleMember -Function Get-RepoRoot, Get-DotEnvPath, Import-DotEnv, Set-DotEnvValue, `
    Assert-Command, Get-FabricToken, Invoke-FabricApi, Get-StorageToken, Send-OneLakeFile, `
    Invoke-FabricLro, Get-KustoToken, Invoke-KustoMgmt

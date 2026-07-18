<#
.SYNOPSIS
    Provision the Fabric Lakehouse, upload landing data, and import the notebooks.

.DESCRIPTION
    Using the service principal from .env, this script:
      1. creates (or reuses) the Lakehouse named $FABRIC_LAKEHOUSE_NAME
      2. uploads data/parquet/*.parquet to the Lakehouse Files/landing/ folder (OneLake DFS)
      3. imports the notebooks in fabric/notebooks/*.ipynb into the workspace
    Writes FABRIC_LAKEHOUSE_ID to .env.

.NOTES
    Idempotent: reuses existing items by display name.
    Requires setup_spn.ps1 to have populated the SPN_* values in .env.
#>
[CmdletBinding()]
param(
    [switch]$SkipUpload,
    [switch]$SkipNotebooks
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'lib\Common.psm1') -Force
$root = Get-RepoRoot
$env = Import-DotEnv

$ws = $env.FABRIC_WORKSPACE_ID
if (-not $ws -or $ws -eq '00000000-0000-0000-0000-000000000000') { throw "FABRIC_WORKSPACE_ID not set in .env." }
$lhName = if ($env.FABRIC_LAKEHOUSE_NAME) { $env.FABRIC_LAKEHOUSE_NAME } else { 'TelcoLakehouse' }

$token = Get-FabricToken -UseSpn

# --- 1. Create or reuse the Lakehouse ---
Write-Host "== Lakehouse '$lhName' ==" -ForegroundColor Cyan
$existing = (Invoke-FabricApi -Method GET -Path "/workspaces/$ws/lakehouses" -Token $token).value |
    Where-Object { $_.displayName -eq $lhName } | Select-Object -First 1
if ($existing) {
    $lakehouseId = $existing.id
    Write-Host "  Reusing existing Lakehouse (id=$lakehouseId)"
} else {
    Write-Host "  Creating Lakehouse..."
    $created = Invoke-FabricLro -Path "/workspaces/$ws/lakehouses" -Token $token `
        -Body @{ displayName = $lhName; description = 'Telco demo Lakehouse (synthetic data)' }
    $lakehouseId = $created.id
    Write-Host "  Created Lakehouse (id=$lakehouseId)"
}
Set-DotEnvValue -Key 'FABRIC_LAKEHOUSE_ID' -Value $lakehouseId

# --- 2. Upload landing parquet ---
if (-not $SkipUpload) {
    Write-Host "== Uploading landing data to Files/landing ==" -ForegroundColor Cyan
    $storageToken = Get-StorageToken -UseSpn
    $parquet = Get-ChildItem (Join-Path $root 'data\parquet\*.parquet')
    if (-not $parquet) { Write-Warning "  No parquet found. Run generate.py first." }
    foreach ($f in $parquet) {
        Send-OneLakeFile -WorkspaceId $ws -LakehouseId $lakehouseId `
            -RelativePath "Files/landing/$($f.Name)" -LocalPath $f.FullName -Token $storageToken
        Write-Host "  uploaded $($f.Name)"
    }
}

# --- 3. Import notebooks ---
if (-not $SkipNotebooks) {
    Write-Host "== Importing notebooks ==" -ForegroundColor Cyan
    $existingNbs = (Invoke-FabricApi -Method GET -Path "/workspaces/$ws/notebooks" -Token $token).value
    foreach ($nb in (Get-ChildItem (Join-Path $root 'fabric\notebooks\*.ipynb') | Sort-Object Name)) {
        $displayName = [System.IO.Path]::GetFileNameWithoutExtension($nb.Name)
        $b64 = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($nb.FullName))
        $body = @{
            displayName = $displayName
            definition  = @{
                format = 'ipynb'
                parts  = @(@{ path = 'notebook-content.ipynb'; payload = $b64; payloadType = 'InlineBase64' })
            }
        }
        $found = $existingNbs | Where-Object { $_.displayName -eq $displayName } | Select-Object -First 1
        if ($found) {
            Invoke-FabricLro -Path "/workspaces/$ws/notebooks/$($found.id)/updateDefinition" -Token $token `
                -Body @{ definition = $body.definition } | Out-Null
            Write-Host "  updated $displayName"
        } else {
            Invoke-FabricLro -Path "/workspaces/$ws/notebooks" -Token $token -Body $body | Out-Null
            Write-Host "  imported $displayName"
        }
    }
}

Write-Host ''
Write-Host "Provisioning complete. Lakehouse id=$lakehouseId" -ForegroundColor Green
Write-Host 'Next: ./scripts/20_load_data.ps1' -ForegroundColor Green

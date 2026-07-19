<#
.SYNOPSIS
    Export a Fabric IQ Ontology (preview) item's definition to local JSON for inspection
    and for regenerating fabric/ontology/ontology.yaml.

.DESCRIPTION
    After you design the ontology by hand in Fabric, run this to pull it back into the repo:
      1. finds the Ontology item in the workspace (by name, default 'TelcoCustomerServiceOntology')
      2. calls the Fabric REST getDefinition API (handles the long-running operation)
      3. decodes the base64 'parts' and writes them under fabric/ontology/_fabric_export/
         preserving the definition's folder layout (.platform, definition.json,
         EntityTypes/<id>/..., RelationshipTypes/<id>/...)
      4. prints a summary of entity types + relationship types found

    The decoded JSON is the input for regenerating ontology.yaml (the design spec). Because the
    ontology definition schema is in preview, this script does the reliable part (fetch + decode);
    share the _fabric_export contents (or commit them) and the YAML can be regenerated to match.

.NOTES
    Reads FABRIC_WORKSPACE_ID (+ SPN creds) from .env. Requires the SPN/user to have access to
    the workspace. Uses the shared Fabric helpers in scripts/lib/Common.psm1.
#>
[CmdletBinding()]
param(
    [string]$OntologyName = 'TelcoOntology',
    [string]$OntologyId,                       # optional: use an explicit item id instead of name
    [switch]$UseSpn = $true
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'lib\Common.psm1') -Force
$root = Get-RepoRoot
$env = Import-DotEnv

$ws = $env.FABRIC_WORKSPACE_ID
if (-not $ws -or $ws -eq '00000000-0000-0000-0000-000000000000') {
    throw 'FABRIC_WORKSPACE_ID not set in .env.'
}
$token = Get-FabricToken -UseSpn:$UseSpn

# --- 1. Resolve the ontology item id ---
if (-not $OntologyId) {
    Write-Host "== Locating ontology '$OntologyName' in workspace ==" -ForegroundColor Cyan
    $items = (Invoke-FabricApi -Method GET -Path "/workspaces/$ws/items" -Token $token).value
    $onto = $items | Where-Object { $_.type -eq 'Ontology' }
    if (-not $onto) {
        throw "No Ontology items found in workspace $ws. Create/design the ontology in Fabric first."
    }
    $match = $onto | Where-Object { $_.displayName -eq $OntologyName } | Select-Object -First 1
    if (-not $match) {
        Write-Host 'Ontology items in this workspace:' -ForegroundColor Yellow
        $onto | ForEach-Object { Write-Host "  - $($_.displayName)  [$($_.id)]" }
        throw "Ontology '$OntologyName' not found. Pass -OntologyName or -OntologyId from the list above."
    }
    $OntologyId = $match.id
}
Write-Host "  ontology id: $OntologyId" -ForegroundColor DarkGray

# --- 2. getDefinition (handles the long-running operation) ---
Write-Host '== Fetching ontology definition ==' -ForegroundColor Cyan
$def = Invoke-FabricLro -Path "/workspaces/$ws/items/$OntologyId/getDefinition" -Token $token -Body @{}
$parts = $def.definition.parts
if (-not $parts) { throw 'getDefinition returned no parts.' }

# --- 3. Decode + write parts, preserving the folder layout ---
$outDir = Join-Path $root 'fabric\ontology\_fabric_export'
if (Test-Path $outDir) { Remove-Item $outDir -Recurse -Force }
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

$entityCount = 0; $relCount = 0
foreach ($p in $parts) {
    $target = Join-Path $outDir ($p.path -replace '/', '\')
    New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
    if ($p.payloadType -eq 'InlineBase64') {
        $bytes = [Convert]::FromBase64String($p.payload)
        [System.IO.File]::WriteAllBytes($target, $bytes)
    } else {
        Set-Content -Path $target -Value $p.payload -Encoding utf8
    }
    if ($p.path -like 'EntityTypes/*/definition.json') { $entityCount++ }
    if ($p.path -like 'RelationshipTypes/*/definition.json') { $relCount++ }
}

# --- 4. Summary ---
Write-Host ''
Write-Host "Exported $($parts.Count) part(s) to fabric/ontology/_fabric_export/" -ForegroundColor Green
Write-Host "  entity types:       $entityCount" -ForegroundColor Green
Write-Host "  relationship types: $relCount" -ForegroundColor Green
Write-Host ''
Write-Host 'Next: commit (or share) fabric/ontology/_fabric_export/ so ontology.yaml can be'
Write-Host 'regenerated from the real Fabric definition.'

// Telco Customer Service AI - Azure infrastructure (Phase 2).
// Deploys Foundry (AI project + model), Azure AI Search, Storage, Key Vault,
// App Service (agent-desktop web app), and observability.
targetScope = 'resourceGroup'

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Short prefix for resource names.')
param namePrefix string = 'telco-ai'

@description('Entra tenant id (for Key Vault).')
param tenantId string = subscription().tenantId

@description('Deploy a chat model into the Foundry account.')
param deployModel bool = true

@description('Model to deploy for the agents.')
param modelName string = 'gpt-4o'
param modelVersion string = '2024-11-20'

@description('Optional Fabric SQL analytics endpoint for the web app (customer_360 fetch).')
param fabricSqlEndpoint string = ''

@description('Create RBAC role assignments (Foundry->Search, WebApp->Key Vault). Requires the deployer to have Owner or User Access Administrator. Set false if you only have Contributor.')
param deployRoleAssignments bool = true

var suffix = uniqueString(resourceGroup().id)
var storageName = toLower('telco${suffix}')
var searchName = '${namePrefix}-search-${suffix}'
var keyVaultName = 'telco-kv-${take(suffix, 8)}'
var foundryAccountName = '${namePrefix}-foundry-${suffix}'
var projectName = 'telco-cs-project'

module observability 'modules/observability.bicep' = {
  name: 'observability'
  params: {
    location: location
    namePrefix: namePrefix
  }
}

module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    location: location
    name: storageName
  }
}

module keyVault 'modules/keyvault.bicep' = {
  name: 'keyvault'
  params: {
    location: location
    name: keyVaultName
    tenantId: tenantId
  }
}

module search 'modules/search.bicep' = {
  name: 'search'
  params: {
    location: location
    name: searchName
  }
}

module foundry 'modules/foundry.bicep' = {
  name: 'foundry'
  params: {
    location: location
    accountName: foundryAccountName
    projectName: projectName
    deployModel: deployModel
    modelName: modelName
    modelVersion: modelVersion
  }
}

module appService 'modules/appservice.bicep' = {
  name: 'appservice'
  params: {
    location: location
    namePrefix: namePrefix
    appInsightsConnectionString: observability.outputs.appInsightsConnectionString
    foundryProjectEndpoint: foundry.outputs.projectEndpoint
    sqlEndpoint: fabricSqlEndpoint
  }
}

module rbac 'modules/rbac.bicep' = if (deployRoleAssignments) {
  name: 'rbac'
  params: {
    searchName: search.outputs.searchName
    keyVaultName: keyVault.outputs.keyVaultName
    foundryPrincipalId: foundry.outputs.accountPrincipalId
    webAppPrincipalId: appService.outputs.webAppPrincipalId
  }
}

output foundryAccountEndpoint string = foundry.outputs.accountEndpoint
output foundryProjectEndpoint string = foundry.outputs.projectEndpoint
output searchEndpoint string = search.outputs.searchEndpoint
output keyVaultName string = keyVault.outputs.keyVaultName
output keyVaultUri string = keyVault.outputs.keyVaultUri
output storageName string = storage.outputs.storageName
output blobEndpoint string = storage.outputs.blobEndpoint
output webAppName string = appService.outputs.webAppName
output webAppUrl string = 'https://${appService.outputs.webAppDefaultHostName}'
output appInsightsConnectionString string = observability.outputs.appInsightsConnectionString

// Azure AI Search for Foundry IQ knowledge sources (product literature / KB).
param location string
param name string
param sku string = 'basic'

resource search 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: name
  location: location
  sku: { name: sku }
  identity: { type: 'SystemAssigned' }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    semanticSearch: 'free'
    publicNetworkAccess: 'enabled'
    // Enable AAD/RBAC for the data plane (indexes, documents) while keeping API keys.
    // Required for both the Foundry managed identity and users to use role-based access.
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http403'
      }
    }
  }
}

output searchName string = search.name
output searchId string = search.id
output searchEndpoint string = 'https://${search.name}.search.windows.net'
output searchPrincipalId string = search.identity.principalId

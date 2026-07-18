// RBAC role assignments wiring Foundry -> Search and Web App -> Key Vault.
param searchName string
param keyVaultName string
param foundryPrincipalId string
param webAppPrincipalId string

resource search 'Microsoft.Search/searchServices@2024-06-01-preview' existing = {
  name: searchName
}
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

// Search Index Data Reader for the Foundry account (agentic retrieval / Foundry IQ).
resource searchDataReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, foundryPrincipalId, 'SearchIndexDataReader')
  scope: search
  properties: {
    principalId: foundryPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '1407120a-92aa-4202-b7e9-c0e197c71c8f')
  }
}

// Search Service Contributor for the Foundry account (index management from Foundry).
resource searchContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, foundryPrincipalId, 'SearchServiceContributor')
  scope: search
  properties: {
    principalId: foundryPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7ca78c08-252a-4471-8644-bb5ff32d4ba0')
  }
}

// Key Vault Secrets User for the Web App managed identity.
resource kvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, webAppPrincipalId, 'KeyVaultSecretsUser')
  scope: keyVault
  properties: {
    principalId: webAppPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

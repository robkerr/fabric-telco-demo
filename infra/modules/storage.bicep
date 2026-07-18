// Storage account (Data Lake Gen2) for AI Search source docs / app assets.
param location string
param name string

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: name
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    isHnsEnabled: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource blob 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource kbContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blob
  name: 'knowledge'
  properties: {
    publicAccess: 'None'
  }
}

output storageName string = storage.name
output storageId string = storage.id
output blobEndpoint string = storage.properties.primaryEndpoints.blob

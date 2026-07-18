// App Service (Linux) hosting the agent-desktop web app.
param location string
param namePrefix string
param linuxFxVersion string = 'PYTHON|3.11'
param appInsightsConnectionString string
param foundryProjectEndpoint string
param sqlEndpoint string = ''
param skuName string = 'B1'

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: '${namePrefix}-plan'
  location: location
  sku: { name: skuName }
  kind: 'linux'
  properties: {
    reserved: true
  }
}

resource site 'Microsoft.Web/sites@2023-12-01' = {
  name: '${namePrefix}-web'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: linuxFxVersion
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsightsConnectionString
        }
        {
          name: 'FOUNDRY_PROJECT_ENDPOINT'
          value: foundryProjectEndpoint
        }
        {
          name: 'FABRIC_SQL_ENDPOINT'
          value: sqlEndpoint
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
      ]
    }
  }
}

output webAppName string = site.name
output webAppDefaultHostName string = site.properties.defaultHostName
output webAppPrincipalId string = site.identity.principalId

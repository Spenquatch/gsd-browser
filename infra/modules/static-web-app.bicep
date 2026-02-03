// modules/static-web-app.bicep — Azure Static Web Apps for dashboard

@description('Azure region')
param location string

@description('Resource name prefix')
param prefix string

resource swa 'Microsoft.Web/staticSites@2023-12-01' = {
  name: '${prefix}-dashboard'
  location: location
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    stagingEnvironmentPolicy: 'Enabled'
    allowConfigFileUpdates: true
    buildProperties: {
      skipGithubActionWorkflowGeneration: true
    }
  }
}

output swaId string = swa.id
output swaDefaultHostname string = swa.properties.defaultHostname
output swaDeploymentToken string = swa.listSecrets().properties.apiKey

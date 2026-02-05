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

// Non-secret outputs only — deployment token should be retrieved via az CLI when needed:
//   az staticwebapp secrets list -n gsd-prod-dashboard --query properties.apiKey -o tsv
output swaId string = swa.id
output swaName string = swa.name
output swaDefaultHostname string = swa.properties.defaultHostname

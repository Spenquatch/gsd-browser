// modules/log-analytics.bicep — Log Analytics workspace

@description('Azure region')
param location string

@description('Resource name prefix')
param prefix string

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${prefix}-logs'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// Non-secret outputs only — consuming modules reference this resource as 'existing'
// and call listKeys() directly to avoid secrets in deployment outputs
output workspaceName string = workspace.name
output workspaceId string = workspace.id
output customerId string = workspace.properties.customerId

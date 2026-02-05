// modules/aca-environment.bicep — ACA Managed Environment

@description('Azure region')
param location string

@description('Resource name prefix')
param prefix string

@description('ACA subnet resource ID')
param acaSubnetId string

@description('Log Analytics workspace name (for existing resource reference)')
param logAnalyticsWorkspaceName string

@description('Log Analytics workspace customer ID')
param logAnalyticsCustomerId string

// Reference Log Analytics workspace as existing to call listKeys() directly
// This avoids passing secrets through module outputs
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsWorkspaceName
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${prefix}-aca-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        // Call listKeys() directly on existing resource to avoid secrets in module outputs
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: acaSubnetId
      internal: false
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    zoneRedundant: false
  }
}

output environmentId string = env.id
output defaultDomain string = env.properties.defaultDomain
output staticIp string = env.properties.staticIp

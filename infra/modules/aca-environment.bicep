// modules/aca-environment.bicep — ACA Managed Environment

@description('Azure region')
param location string

@description('Resource name prefix')
param prefix string

@description('ACA subnet resource ID')
param acaSubnetId string

@description('Log Analytics workspace customer ID')
param logAnalyticsCustomerId string

@description('Log Analytics workspace shared key')
@secure()
param logAnalyticsSharedKey string

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${prefix}-aca-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsSharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: acaSubnetId
      internal: false
    }
    zoneRedundant: false
  }
}

output environmentId string = env.id
output defaultDomain string = env.properties.defaultDomain
output staticIp string = env.properties.staticIp

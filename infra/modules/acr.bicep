// modules/acr.bicep — Azure Container Registry

@description('Azure region')
param location string

@description('Resource name prefix (alphanumeric only for ACR)')
param prefix string

// ACR names must be alphanumeric, 5-50 chars
var acrName = replace('${prefix}acr', '-', '')

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
}

// Non-secret outputs only — consuming modules reference this resource as 'existing'
// and call listCredentials() directly to avoid secrets in deployment outputs
output acrId string = acr.id
output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer

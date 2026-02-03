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

output acrId string = acr.id
output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
output acrUsername string = acr.listCredentials().username
output acrPassword string = acr.listCredentials().passwords[0].value

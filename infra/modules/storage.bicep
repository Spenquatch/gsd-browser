// modules/storage.bicep — Blob Storage + Private Endpoint + DNS

@description('Azure region')
param location string

@description('Resource name prefix')
param prefix string

@description('VNet ID for DNS zone link')
param vnetId string

@description('Subnet ID for private endpoint')
param privateEndpointSubnetId string

// Storage account names: 3-24 lowercase alphanumeric
var storageAccountName = replace('${prefix}store', '-', '')

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    accessTier: 'Hot'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource artifactsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'gsd-artifacts'
  properties: {
    publicAccess: 'None'
  }
}

// Private DNS zone for Blob
resource dnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.blob.core.windows.net'
  location: 'global'
}

resource dnsVnetLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: dnsZone
  name: '${prefix}-blob-vnet-link'
  location: 'global'
  properties: {
    virtualNetwork: {
      id: vnetId
    }
    registrationEnabled: false
  }
}

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: '${storageAccountName}-pe'
  location: location
  properties: {
    subnet: {
      id: privateEndpointSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: '${storageAccountName}-plsc'
        properties: {
          privateLinkServiceId: storage.id
          groupIds: [
            'blob'
          ]
        }
      }
    ]
  }
}

resource dnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: privateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'privatelink-blob'
        properties: {
          privateDnsZoneId: dnsZone.id
        }
      }
    ]
  }
}

// Non-secret outputs only — consuming modules reference this resource as 'existing'
// and call listKeys() directly to avoid secrets in deployment outputs
output storageAccountName string = storage.name
output blobEndpoint string = storage.properties.primaryEndpoints.blob
output accessKeyId string = storage.name
output storageId string = storage.id

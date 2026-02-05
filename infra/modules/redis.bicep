// modules/redis.bicep — Azure Cache for Redis + Private Endpoint + DNS

@description('Azure region')
param location string

@description('Resource name prefix')
param prefix string

@description('VNet ID for DNS zone link')
param vnetId string

@description('Subnet ID for private endpoint')
param privateEndpointSubnetId string

var redisName = '${prefix}-redis'

resource redis 'Microsoft.Cache/redis@2023-08-01' = {
  name: redisName
  location: location
  properties: {
    sku: {
      name: 'Standard'
      family: 'C'
      capacity: 2
    }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    redisConfiguration: {
      'maxmemory-policy': 'noeviction'
    }
  }
}

// Private DNS zone for Redis
resource dnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.redis.cache.windows.net'
  location: 'global'
}

resource dnsVnetLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: dnsZone
  name: '${prefix}-redis-vnet-link'
  location: 'global'
  properties: {
    virtualNetwork: {
      id: vnetId
    }
    registrationEnabled: false
  }
}

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: '${redisName}-pe'
  location: location
  properties: {
    subnet: {
      id: privateEndpointSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: '${redisName}-plsc'
        properties: {
          privateLinkServiceId: redis.id
          groupIds: [
            'redisCache'
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
        name: 'privatelink-redis'
        properties: {
          privateDnsZoneId: dnsZone.id
        }
      }
    ]
  }
}

// Non-secret outputs only — consuming modules reference this resource as 'existing'
// and call listKeys() directly to avoid secrets in deployment outputs
output redisName string = redis.name
output redisHost string = redis.properties.hostName
output redisPort int = redis.properties.sslPort
output redisId string = redis.id

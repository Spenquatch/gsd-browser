// modules/aca-app-worker.bicep — Worker container app (port 5009, WebSocket)
//
// This module references Redis, Storage, and ACR as existing resources and calls
// listKeys()/listCredentials() directly to construct secrets. This avoids passing
// secrets through module outputs, which would expose them in deployment metadata.

@description('Azure region')
param location string

@description('Resource name prefix')
param prefix string

@description('ACA environment ID')
param environmentId string

@description('ACR name (for existing resource reference)')
param acrName string

@description('ACR login server')
param acrLoginServer string

@description('Container image tag')
param imageTag string = 'latest'

@description('Redis name (for existing resource reference)')
param redisName string

@description('Redis host')
param redisHost string

@description('Redis SSL port')
param redisPort int

@description('Anthropic API key')
@secure()
param anthropicApiKey string

@description('Storage account name (for existing resource reference)')
param storageAccountName string

@description('S3-compatible blob endpoint URL')
param s3EndpointUrl string

@description('S3 bucket name')
param s3Bucket string

// Reference ACR as existing to call listCredentials() directly
resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: acrName
}

// Reference Redis as existing to call listKeys() directly
resource redis 'Microsoft.Cache/redis@2023-08-01' existing = {
  name: redisName
}

// Reference Storage as existing to call listKeys() directly
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource workerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-worker'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 5009
        transport: 'auto'
        stickySessions: {
          affinity: 'sticky'
        }
      }
      registries: [
        {
          server: acrLoginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        // Secrets are derived directly from existing resource references, avoiding
        // secrets in module outputs. listKeys()/listCredentials() calls are still
        // in the deployment graph but never appear in deployment outputs.
        { name: 'acr-password', value: acr.listCredentials().passwords[0].value }
        { name: 'docket-url', value: 'rediss://:${redis.listKeys().primaryKey}@${redisHost}:${redisPort}/0' }
        { name: 'anthropic-api-key', value: anthropicApiKey }
        { name: 's3-secret-access-key', value: storage.listKeys().keys[0].value }
      ]
    }
    template: {
      containers: [
        {
          name: 'gsd-worker'
          image: '${acrLoginServer}/gsd-browser:${imageTag}'
          command: ['gsd-browser']
          args: ['worker']
          resources: {
            cpu: json('2.0')
            memory: '4Gi'
          }
          env: [
            { name: 'GSD_DEPLOYMENT_ENV', value: 'prod' }
            { name: 'GSD_USE_FASTMCP_V2', value: 'true' }
            { name: 'FASTMCP_DOCKET_URL', secretRef: 'docket-url' }
            { name: 'FASTMCP_DOCKET_NAME', value: 'gsd' }
            { name: 'FASTMCP_DOCKET_CONCURRENCY', value: '4' }
            // Azure Blob Storage (preferred for artifacts)
            { name: 'GSD_AZURE_STORAGE_ACCOUNT', value: storageAccountName }
            { name: 'GSD_AZURE_BLOB_CONTAINER', value: s3Bucket }
            // S3-compatible fallback (kept for backward compatibility)
            { name: 'GSD_S3_ENDPOINT_URL', value: s3EndpointUrl }
            { name: 'GSD_S3_BUCKET', value: s3Bucket }
            { name: 'GSD_S3_REGION', value: 'us-east-1' }
            { name: 'GSD_S3_ACCESS_KEY_ID', value: storageAccountName }
            { name: 'GSD_S3_SECRET_ACCESS_KEY', secretRef: 's3-secret-access-key' }
            { name: 'GSD_S3_SSE_MODE', value: 'none' }
            { name: 'GSD_ARTIFACT_DELIVERY_MODE', value: 'both' }
            { name: 'GSD_PRESIGNED_URL_TTL_S', value: '900' }
            { name: 'ANTHROPIC_API_KEY', secretRef: 'anthropic-api-key' }
            { name: 'GSD_LLM_PROVIDER', value: 'anthropic' }
            { name: 'GSD_MODEL', value: 'claude-haiku-4-5' }
          ]
          // Worker is a Docket task processor without HTTP server.
          // ACA will restart if the container exits. No probe needed.
          probes: []
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 20
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
    }
  }
}

output fqdn string = workerApp.properties.configuration.ingress.fqdn
output appId string = workerApp.id
output principalId string = workerApp.identity.principalId

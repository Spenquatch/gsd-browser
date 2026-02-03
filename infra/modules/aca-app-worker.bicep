// modules/aca-app-worker.bicep — Worker container app (port 5009, WebSocket)

@description('Azure region')
param location string

@description('Resource name prefix')
param prefix string

@description('ACA environment ID')
param environmentId string

@description('ACR login server')
param acrLoginServer string

@description('ACR username')
param acrUsername string

@description('ACR password')
@secure()
param acrPassword string

@description('Container image tag')
param imageTag string = 'latest'

@description('Redis Docket URL (rediss://...)')
@secure()
param docketUrl string

@description('Anthropic API key')
@secure()
param anthropicApiKey string

@description('S3-compatible blob endpoint URL')
param s3EndpointUrl string

@description('S3 bucket name')
param s3Bucket string

@description('S3 access key ID (storage account name)')
param s3AccessKeyId string

@description('S3 secret access key')
@secure()
param s3SecretAccessKey string

resource workerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-worker'
  location: location
  properties: {
    managedEnvironmentId: environmentId
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
          username: acrUsername
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        { name: 'acr-password', value: acrPassword }
        { name: 'docket-url', value: docketUrl }
        { name: 'anthropic-api-key', value: anthropicApiKey }
        { name: 's3-secret-access-key', value: s3SecretAccessKey }
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
            { name: 'GSD_S3_ENDPOINT_URL', value: s3EndpointUrl }
            { name: 'GSD_S3_BUCKET', value: s3Bucket }
            { name: 'GSD_S3_REGION', value: 'us-east-1' }
            { name: 'GSD_S3_ACCESS_KEY_ID', value: s3AccessKeyId }
            { name: 'GSD_S3_SECRET_ACCESS_KEY', secretRef: 's3-secret-access-key' }
            { name: 'GSD_S3_SSE_MODE', value: 'none' }
            { name: 'GSD_ARTIFACT_DELIVERY_MODE', value: 'both' }
            { name: 'GSD_PRESIGNED_URL_TTL_S', value: '900' }
            { name: 'ANTHROPIC_API_KEY', secretRef: 'anthropic-api-key' }
            { name: 'GSD_LLM_PROVIDER', value: 'anthropic' }
            { name: 'GSD_MODEL', value: 'claude-haiku-4-5' }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: 5009
              }
              periodSeconds: 15
              failureThreshold: 3
            }
          ]
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

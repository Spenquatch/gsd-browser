// modules/aca-app-api.bicep — API server container app (port 8080)
//
// This module references Redis and ACR as existing resources and calls
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

@description('Clerk JWKS URL')
param jwtJwksUrl string

@description('Clerk JWT issuer')
param jwtIssuer string

@description('Clerk JWT audience')
param jwtAudience string

@description('Allowed origins for CORS (comma-separated URLs)')
param allowedOrigins string = ''

// Reference ACR as existing to call listCredentials() directly
resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: acrName
}

// Reference Redis as existing to call listKeys() directly
resource redis 'Microsoft.Cache/redis@2023-08-01' existing = {
  name: redisName
}

resource apiApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-api'
  location: location
  properties: {
    managedEnvironmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        transport: 'auto'
        corsPolicy: {
          allowedOrigins: ['*']
          allowedMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
          allowedHeaders: ['*']
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
      ]
    }
    template: {
      containers: [
        {
          name: 'gsd-api'
          image: '${acrLoginServer}/gsd-browser:${imageTag}'
          command: ['uvicorn']
          args: [
            'gsd_browser.fastmcp_v2_http:app'
            '--host'
            '0.0.0.0'
            '--port'
            '8080'
            '--log-level'
            'info'
          ]
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: [
            { name: 'GSD_DEPLOYMENT_ENV', value: 'prod' }
            { name: 'GSD_TRANSPORT', value: 'http' }
            { name: 'FASTMCP_DOCKET_URL', secretRef: 'docket-url' }
            { name: 'FASTMCP_DOCKET_NAME', value: 'gsd' }
            { name: 'FASTMCP_DOCKET_CONCURRENCY', value: '0' }
            { name: 'GSD_JWT_JWKS_URL', value: jwtJwksUrl }
            { name: 'GSD_JWT_ISSUER', value: jwtIssuer }
            { name: 'GSD_JWT_AUDIENCE', value: jwtAudience }
            { name: 'GSD_JWT_TENANT_ID_CLAIM', value: 'tenant_id' }
            { name: 'GSD_JWT_SUBJECT_ID_CLAIM', value: 'sub' }
            { name: 'ANTHROPIC_API_KEY', secretRef: 'anthropic-api-key' }
            { name: 'GSD_LLM_PROVIDER', value: 'anthropic' }
            { name: 'GSD_MODEL', value: 'claude-haiku-4-5' }
            { name: 'GSD_HTTP_ALLOWED_ORIGINS', value: allowedOrigins }
            { name: 'GSD_HTTP_ALLOW_NULL_ORIGIN', value: 'true' }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/.well-known/oauth-protected-resource'
                port: 8080
              }
              periodSeconds: 10
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/.well-known/oauth-protected-resource'
                port: 8080
              }
              periodSeconds: 5
              failureThreshold: 5
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 5
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
}

output fqdn string = apiApp.properties.configuration.ingress.fqdn
output appId string = apiApp.id

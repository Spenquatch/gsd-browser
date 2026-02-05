// modules/aca-app-mgmt.bicep — Management API container app (port 8081)
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

@description('Clerk JWKS URL')
param jwtJwksUrl string

@description('Clerk JWT issuer')
param jwtIssuer string

@description('Clerk JWT audience')
param jwtAudience string

@description('Allowed origins for CORS (comma-separated URLs)')
param allowedOrigins string = ''

@description('ACA environment domain (e.g. yellowplant-...eastus.azurecontainerapps.io)')
param acaEnvironmentDomain string

// Reference ACR as existing to call listCredentials() directly
resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: acrName
}

// Reference Redis as existing to call listKeys() directly
resource redis 'Microsoft.Cache/redis@2023-08-01' existing = {
  name: redisName
}

resource mgmtApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-mgmt'
  location: location
  properties: {
    managedEnvironmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8081
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
      ]
    }
    template: {
      containers: [
        {
          name: 'gsd-mgmt'
          image: '${acrLoginServer}/gsd-browser:${imageTag}'
          command: ['uvicorn']
          args: [
            'gsd_browser.management_api.app:app'
            '--host'
            '0.0.0.0'
            '--port'
            '8081'
            '--log-level'
            'info'
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'GSD_DEPLOYMENT_ENV', value: 'prod' }
            { name: 'FASTMCP_DOCKET_URL', secretRef: 'docket-url' }
            { name: 'FASTMCP_DOCKET_NAME', value: 'gsd' }
            // Streaming base URL advertised to the dashboard (ADR-0024)
            { name: 'GSD_STREAMING_PUBLIC_HOST', value: '${prefix}-worker.${acaEnvironmentDomain}' }
            { name: 'GSD_STREAMING_PUBLIC_SCHEME', value: 'https' }
            { name: 'GSD_JWT_JWKS_URL', value: jwtJwksUrl }
            { name: 'GSD_JWT_ISSUER', value: jwtIssuer }
            { name: 'GSD_JWT_AUDIENCE', value: jwtAudience }
            { name: 'GSD_JWT_TENANT_ID_CLAIM', value: 'tenant_id' }
            { name: 'GSD_JWT_SUBJECT_ID_CLAIM', value: 'sub' }
            { name: 'GSD_HTTP_ALLOWED_ORIGINS', value: allowedOrigins }
            // Allow server-to-server requests (no Origin header) for CLI scripts and internal tooling
            { name: 'GSD_HTTP_ALLOW_NULL_ORIGIN', value: 'true' }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: 8081
              }
              periodSeconds: 10
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/healthz'
                port: 8081
              }
              periodSeconds: 5
              failureThreshold: 5
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '30'
              }
            }
          }
        ]
      }
    }
  }
}

output fqdn string = mgmtApp.properties.configuration.ingress.fqdn
output appId string = mgmtApp.id

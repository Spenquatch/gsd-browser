// modules/aca-app-api.bicep — API server container app (port 8080)

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

@description('Clerk JWKS URL')
param jwtJwksUrl string

@description('Clerk JWT issuer')
param jwtIssuer string

@description('Clerk JWT audience')
param jwtAudience string

resource apiApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-api'
  location: location
  properties: {
    managedEnvironmentId: environmentId
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
          username: acrUsername
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        { name: 'acr-password', value: acrPassword }
        { name: 'docket-url', value: docketUrl }
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

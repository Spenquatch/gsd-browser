// modules/aca-app-mgmt.bicep — Management API container app (port 8081)

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

@description('Clerk JWKS URL')
param jwtJwksUrl string

@description('Clerk JWT issuer')
param jwtIssuer string

@description('Clerk JWT audience')
param jwtAudience string

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
          username: acrUsername
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        { name: 'acr-password', value: acrPassword }
        { name: 'docket-url', value: docketUrl }
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
            { name: 'GSD_JWT_JWKS_URL', value: jwtJwksUrl }
            { name: 'GSD_JWT_ISSUER', value: jwtIssuer }
            { name: 'GSD_JWT_AUDIENCE', value: jwtAudience }
            { name: 'GSD_JWT_TENANT_ID_CLAIM', value: 'tenant_id' }
            { name: 'GSD_JWT_SUBJECT_ID_CLAIM', value: 'sub' }
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

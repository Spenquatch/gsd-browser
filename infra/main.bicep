// main.bicep — Orchestrator (subscription-scoped deployment)
//
// Deploys the full GSD browser automation platform to Azure:
//   VNet → Log Analytics → ACR → Redis → Storage → ACA Env → Apps → SWA
//
// Usage:
//   az deployment sub create \
//     --location eastus \
//     --template-file infra/main.bicep \
//     --parameters infra/parameters/prod.bicepparam

targetScope = 'subscription'

// ── Parameters ──────────────────────────────────────────────────────────

@description('Azure region for all resources')
param location string = 'eastus'

@description('Resource group name')
param resourceGroupName string = 'gsd-prod-rg'

@description('Resource name prefix')
param prefix string = 'gsd-prod'

@description('Container image tag to deploy')
param imageTag string = 'latest'

@description('Anthropic API key')
@secure()
param anthropicApiKey string

@description('Clerk JWKS URL')
param jwtJwksUrl string = 'https://fresh-sheepdog-88.clerk.accounts.dev/.well-known/jwks.json'

@description('Clerk JWT issuer')
param jwtIssuer string = 'https://fresh-sheepdog-88.clerk.accounts.dev'

@description('Clerk JWT audience')
param jwtAudience string = 'gsd'

@description('Allowed origins for CORS (comma-separated URLs)')
param allowedOrigins string = ''

// ── Resource Group ──────────────────────────────────────────────────────

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
}

// ── Foundation Layer ────────────────────────────────────────────────────

module vnet 'modules/vnet.bicep' = {
  name: 'vnet'
  scope: rg
  params: {
    location: location
    prefix: prefix
  }
}

module logAnalytics 'modules/log-analytics.bicep' = {
  name: 'log-analytics'
  scope: rg
  params: {
    location: location
    prefix: prefix
  }
}

module acr 'modules/acr.bicep' = {
  name: 'acr'
  scope: rg
  params: {
    location: location
    prefix: prefix
  }
}

// ── Data Tier (depends on VNet) ─────────────────────────────────────────

module redis 'modules/redis.bicep' = {
  name: 'redis'
  scope: rg
  params: {
    location: location
    prefix: prefix
    vnetId: vnet.outputs.vnetId
    privateEndpointSubnetId: vnet.outputs.privateEndpointSubnetId
  }
}

module storage 'modules/storage.bicep' = {
  name: 'storage'
  scope: rg
  params: {
    location: location
    prefix: prefix
    vnetId: vnet.outputs.vnetId
    privateEndpointSubnetId: vnet.outputs.privateEndpointSubnetId
  }
}

// ── ACA Environment (depends on VNet + Logs) ────────────────────────────

module acaEnv 'modules/aca-environment.bicep' = {
  name: 'aca-environment'
  scope: rg
  params: {
    location: location
    prefix: prefix
    acaSubnetId: vnet.outputs.acaSubnetId
    logAnalyticsWorkspaceName: logAnalytics.outputs.workspaceName
    logAnalyticsCustomerId: logAnalytics.outputs.customerId
    // Note: sharedKey is no longer passed — aca-environment.bicep references
    // the workspace as 'existing' and calls listKeys() directly
  }
}

// ── Container Apps (depends on ACA Env + Data Tier + ACR) ───────────────

module apiApp 'modules/aca-app-api.bicep' = {
  name: 'aca-app-api'
  scope: rg
  params: {
    location: location
    prefix: prefix
    environmentId: acaEnv.outputs.environmentId
    acaEnvironmentDomain: acaEnv.outputs.defaultDomain
    acrName: acr.outputs.acrName
    acrLoginServer: acr.outputs.acrLoginServer
    imageTag: imageTag
    redisName: redis.outputs.redisName
    redisHost: redis.outputs.redisHost
    redisPort: redis.outputs.redisPort
    anthropicApiKey: anthropicApiKey
    storageAccountName: storage.outputs.storageAccountName
    azureBlobContainer: 'gsd-artifacts'
    jwtJwksUrl: jwtJwksUrl
    jwtIssuer: jwtIssuer
    jwtAudience: jwtAudience
    allowedOrigins: allowedOrigins
    // Note: docketUrl and acrPassword are no longer passed — aca-app-api.bicep
    // references Redis/ACR as 'existing' and calls listKeys()/listCredentials() directly
  }
}

module mgmtApp 'modules/aca-app-mgmt.bicep' = {
  name: 'aca-app-mgmt'
  scope: rg
  params: {
    location: location
    prefix: prefix
    environmentId: acaEnv.outputs.environmentId
    acaEnvironmentDomain: acaEnv.outputs.defaultDomain
    acrName: acr.outputs.acrName
    acrLoginServer: acr.outputs.acrLoginServer
    imageTag: imageTag
    redisName: redis.outputs.redisName
    redisHost: redis.outputs.redisHost
    redisPort: redis.outputs.redisPort
    jwtJwksUrl: jwtJwksUrl
    jwtIssuer: jwtIssuer
    jwtAudience: jwtAudience
    allowedOrigins: allowedOrigins
    // Note: docketUrl and acrPassword are no longer passed — aca-app-mgmt.bicep
    // references Redis/ACR as 'existing' and calls listKeys()/listCredentials() directly
  }
}

module workerApp 'modules/aca-app-worker.bicep' = {
  name: 'aca-app-worker'
  scope: rg
  params: {
    location: location
    prefix: prefix
    environmentId: acaEnv.outputs.environmentId
    acaEnvironmentDomain: acaEnv.outputs.defaultDomain
    acrName: acr.outputs.acrName
    acrLoginServer: acr.outputs.acrLoginServer
    imageTag: imageTag
    redisName: redis.outputs.redisName
    redisHost: redis.outputs.redisHost
    redisPort: redis.outputs.redisPort
    anthropicApiKey: anthropicApiKey
    jwtJwksUrl: jwtJwksUrl
    jwtIssuer: jwtIssuer
    jwtAudience: jwtAudience
    allowedOrigins: allowedOrigins
    storageAccountName: storage.outputs.storageAccountName
    s3EndpointUrl: storage.outputs.blobEndpoint
    s3Bucket: 'gsd-artifacts'
    // Note: docketUrl, acrPassword, and s3SecretAccessKey are no longer passed —
    // aca-app-worker.bicep references Redis/ACR/Storage as 'existing' and calls
    // listKeys()/listCredentials() directly
  }
}

// ── RBAC for Managed Identity ──────────────────────────────────────────

// Grant worker app Storage Blob Data Contributor role for Azure Blob artifacts
module workerStorageRbac 'modules/storage-rbac.bicep' = {
  name: 'worker-storage-rbac'
  scope: rg
  params: {
    storageAccountName: storage.outputs.storageAccountName
    principalId: workerApp.outputs.principalId
  }
}

// Grant api app Storage Blob Data Contributor role so it can generate SAS URLs for artifacts.
module apiStorageRbac 'modules/storage-rbac.bicep' = {
  name: 'api-storage-rbac'
  scope: rg
  params: {
    storageAccountName: storage.outputs.storageAccountName
    principalId: apiApp.outputs.principalId
  }
}

// ── Static Web App (dashboard) ──────────────────────────────────────────

module swa 'modules/static-web-app.bicep' = {
  name: 'static-web-app'
  scope: rg
  params: {
    location: 'eastus2' // SWA not available in eastus; nearest region
    prefix: prefix
  }
}

// ── Monitoring / Alerts ─────────────────────────────────────────────────

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  scope: rg
  params: {
    prefix: prefix
    logAnalyticsWorkspaceId: logAnalytics.outputs.workspaceId
    apiAppId: apiApp.outputs.appId
    workerAppId: workerApp.outputs.appId
    redisId: redis.outputs.redisId
  }
}

// ── Outputs ─────────────────────────────────────────────────────────────

output resourceGroupName string = rg.name
output acrLoginServer string = acr.outputs.acrLoginServer
output apiFqdn string = apiApp.outputs.fqdn
output mgmtFqdn string = mgmtApp.outputs.fqdn
output workerFqdn string = workerApp.outputs.fqdn
output dashboardUrl string = 'https://${swa.outputs.swaDefaultHostname}'
output acaEnvironmentDomain string = acaEnv.outputs.defaultDomain

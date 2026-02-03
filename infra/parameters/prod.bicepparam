using '../main.bicep'

param location = 'eastus'
param resourceGroupName = 'gsd-prod-rg'
param prefix = 'gsd-prod'
param imageTag = 'latest'

// Clerk auth configuration
param jwtJwksUrl = 'https://fresh-sheepdog-88.clerk.accounts.dev/.well-known/jwks.json'
param jwtIssuer = 'https://fresh-sheepdog-88.clerk.accounts.dev'
param jwtAudience = 'gsd'

// Secrets — supplied at deploy time via --parameters or environment
// param anthropicApiKey = <set via deploy.sh>

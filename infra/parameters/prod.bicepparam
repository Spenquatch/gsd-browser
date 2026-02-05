using '../main.bicep'

param location = 'eastus'
param resourceGroupName = 'gsd-prod-rg'
param prefix = 'gsd-prod'
param imageTag = 'latest'

// Clerk auth configuration
param jwtJwksUrl = 'https://clerk.browse.buildconnectors.com/.well-known/jwks.json'
param jwtIssuer = 'https://clerk.browse.buildconnectors.com'
param jwtAudience = 'gsd'

// CORS allowed origins (dashboard + APIs)
param allowedOrigins = 'https://browse.buildconnectors.com,https://zealous-wave-0ed3a980f.1.azurestaticapps.net,https://gsd-prod-mgmt.yellowplant-7a34cb33.eastus.azurecontainerapps.io,https://gsd-prod-api.yellowplant-7a34cb33.eastus.azurecontainerapps.io'

// Secrets — read from environment variable at deploy time
param anthropicApiKey = readEnvironmentVariable('ANTHROPIC_API_KEY')

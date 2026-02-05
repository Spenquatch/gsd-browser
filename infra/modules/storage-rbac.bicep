// modules/storage-rbac.bicep — RBAC role assignments for Storage Account
//
// Grants Storage Blob Data Contributor role to specified principals.
// This enables Azure Blob operations via Managed Identity.

@description('Storage account name')
param storageAccountName string

@description('Principal ID to grant access to')
param principalId string

@description('Principal type (ServicePrincipal for managed identity)')
param principalType string = 'ServicePrincipal'

// Reference storage account as existing
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

// Storage Blob Data Contributor role definition
// Allows read, write, and delete access to Azure Storage blob containers and data
var storageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, principalId, storageBlobDataContributorRoleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRoleId)
    principalId: principalId
    principalType: principalType
  }
}

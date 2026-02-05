// modules/monitoring.bicep — Alert rules for ACA apps and Redis

@description('Resource name prefix')
param prefix string

@description('Log Analytics workspace resource ID')
param logAnalyticsWorkspaceId string

@description('API container app resource ID')
param apiAppId string

@description('Worker container app resource ID')
param workerAppId string

@description('Redis cache resource ID')
param redisId string

// Action group for alert notifications
resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: '${prefix}-alerts-ag'
  location: 'global'
  properties: {
    groupShortName: 'gsd-alerts'
    enabled: true
    // Add email/webhook receivers here when ready
    emailReceivers: []
    webhookReceivers: []
  }
}

// Alert: API server high error rate (5xx > 10 in 5 min)
resource apiErrorAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: '${prefix}-api-high-errors'
  location: 'global'
  properties: {
    description: 'API server returning high rate of 5xx errors'
    severity: 2
    enabled: true
    scopes: [apiAppId]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'HighServerErrors'
          criterionType: 'StaticThresholdCriterion'
          metricName: 'Requests'
          metricNamespace: 'Microsoft.App/containerApps'
          dimensions: [
            {
              name: 'statusCodeCategory'
              operator: 'Include'
              values: ['5xx']
            }
          ]
          operator: 'GreaterThan'
          threshold: 10
          timeAggregation: 'Total'
        }
      ]
    }
    actions: [
      {
        actionGroupId: actionGroup.id
      }
    ]
  }
}

// Alert: Worker high replica count (> 15 indicates load spike)
resource workerScaleAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: '${prefix}-worker-high-replicas'
  location: 'global'
  properties: {
    description: 'Worker replica count approaching max (20)'
    severity: 3
    enabled: true
    scopes: [workerAppId]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'HighReplicaCount'
          criterionType: 'StaticThresholdCriterion'
          metricName: 'Replicas'
          metricNamespace: 'Microsoft.App/containerApps'
          operator: 'GreaterThan'
          threshold: 15
          timeAggregation: 'Maximum'
        }
      ]
    }
    actions: [
      {
        actionGroupId: actionGroup.id
      }
    ]
  }
}

// Log-based alert: Any container restart loops
resource restartAlert 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: '${prefix}-container-restart-loop'
  location: resourceGroup().location
  properties: {
    description: 'Container restart loop detected'
    severity: 2
    enabled: true
    scopes: [logAnalyticsWorkspaceId]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    criteria: {
      allOf: [
        {
          query: '''
            ContainerAppSystemLogs_CL
            | where Reason_s == "BackOff" or Reason_s == "CrashLoopBackOff"
            | summarize RestartCount = count() by ContainerAppName_s, bin(TimeGenerated, 5m)
            | where RestartCount > 3
          '''
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
        }
      ]
    }
    actions: {
      actionGroups: [actionGroup.id]
    }
  }
}

// Alert: Redis memory usage > 80%
// With noeviction policy, high memory usage can cause write failures.
// This alert triggers before reaching 100% to allow remediation time.
resource redisMemoryAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: '${prefix}-redis-high-memory'
  location: 'global'
  properties: {
    description: 'Redis memory usage exceeds 80%. Consider cleanup or scaling. See docs/ops/RUNBOOK-redis-memory.md'
    severity: 2
    enabled: true
    scopes: [redisId]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'HighMemoryUsage'
          criterionType: 'StaticThresholdCriterion'
          metricName: 'usedmemorypercentage'
          metricNamespace: 'Microsoft.Cache/redis'
          operator: 'GreaterThan'
          threshold: 80
          timeAggregation: 'Average'
        }
      ]
    }
    actions: [
      {
        actionGroupId: actionGroup.id
      }
    ]
  }
}

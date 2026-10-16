import type { ExecutionsAPI } from '@syntara/contracts'

import { activityExecutions } from './activityExecutions'
import { executions } from './executions'
import { workflows } from './workflows'

type ActivityData = ExecutionsAPI.components['schemas']['ActivityData']
type ActivityExecution = ExecutionsAPI.components['schemas']['ActivityExecution']
type Execution = ExecutionsAPI.components['schemas']['Execution']

function toActivityData(activity: ActivityExecution): ActivityData {
  return {
    activity_id: activity.activity_name ?? activity.id,
    status: activity.status,
    error_details: activity.error_details,
    output_data: activity.output_data,
    started_at: activity.started_at,
    completed_at: activity.completed_at,
    stall_alert_at: activity.stall_alert_at,
  }
}

/** Build full execution detail from live stores (matches GET /executions/{id}?include=...). */
export function getExecutionDetail(executionId: string): Execution | undefined {
  const execution = executions.find((item) => item.id === executionId)
  if (!execution) return undefined

  const workflow = workflows.find((item) => item.id === execution.workflow_id)
  return {
    ...execution,
    activities: (activityExecutions[execution.id] ?? []).map(toActivityData),
    workflow_definition: workflow?.version?.workflow_definition,
  }
}

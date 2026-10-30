import type { ActivityExecution } from '@syntara/contracts'

import type { ChildExecutionActivities } from './hooks/useSubWorkflowChildData'

type ChildActivitySummary = {
  activity_name: string
  node_type: string
  status: string
  started_at: string | null
  completed_at: string | null
  output_data: Record<string, unknown> | null
  error_details: string | null
}

function toSummary(activity: ActivityExecution): ChildActivitySummary {
  return {
    activity_name: activity.activity_name,
    node_type: activity.node_type,
    status: activity.status,
    started_at: activity.started_at ?? null,
    completed_at: activity.completed_at ?? null,
    output_data: activity.output_data ?? null,
    error_details: activity.error_details ?? null,
  }
}

/**
 * Compose the enriched Output object for a sub-workflow node at
 * DISPLAY TIME. Combines the node's persisted ``output_data`` and the mapped
 * ``input_parameters`` with the child's real persisted activities (fetched
 * read-only via the children + activities endpoints).
 *
 * This is an inspection view only: ``child_activities`` is NOT persisted on the
 * node's ``output_data`` and is NOT the value available to downstream workflow
 * nodes. ``ActivityExecution`` has no friendly display name, so child activity
 * entries carry ``activity_name`` (the node id) only.
 */
export function composeSubWorkflowOutput({
  outputData,
  inputParameters,
  nodeStatus,
  childData,
}: {
  outputData: Record<string, unknown> | null
  inputParameters: unknown
  nodeStatus: string | null | undefined
  childData: ChildExecutionActivities[]
}): Record<string, unknown> {
  const base = outputData ?? {}
  const common = {
    status: nodeStatus ?? null,
    workflow_id: base.workflow_id ?? null,
    workflow_name: base.workflow_name ?? null,
    child_workflow_version: base.child_workflow_version ?? null,
    input_parameters: inputParameters ?? {},
  }

  if (childData.length <= 1) {
    const only = childData[0]
    return {
      ...common,
      child_execution_id: base.child_execution_id ?? only?.child.id ?? null,
      child_activities: only ? only.activities.map(toSummary) : [],
    }
  }

  // for_each: keep each child execution's activities grouped with its own id.
  return {
    ...common,
    child_executions: childData.map((entry) => ({
      child_execution_id: entry.child.id,
      workflow_name: entry.child.workflow_name ?? null,
      child_workflow_version: entry.child.workflow_version ?? null,
      status: entry.child.status ?? null,
      child_activities: entry.activities.map(toSummary),
    })),
  }
}

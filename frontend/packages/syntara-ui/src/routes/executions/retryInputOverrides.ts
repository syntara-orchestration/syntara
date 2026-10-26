import type { ExecutionsAPI } from '@syntara/contracts'

import type { WorkflowDefShape } from '../builder/ExecutionDetailsPanel'
import { parseCompositeKey } from '../workflows/execution/utils/activityState'

type ActivityDefinition = NonNullable<WorkflowDefShape['nodes']>[number]

export type ExecutionActivity =
  ExecutionsAPI.components['schemas']['ActivityData'] | ExecutionsAPI.components['schemas']['ActivityExecution']

export type RetryInputOverrideTarget = Readonly<{
  id: string
  name: string
  parameterNames: string[]
  failedActivityName?: string
}>

export function getRetryInputOverrideTargets(
  pointIds: string[],
  workflowDefinition: WorkflowDefShape | null | undefined,
  activityNameMap: ReadonlyMap<string, string>,
  activities: ExecutionActivity[]
): RetryInputOverrideTarget[] {
  const roots = [
    ...(workflowDefinition?.triggers ?? []),
    ...(workflowDefinition?.nodes ?? []),
    ...(workflowDefinition?.workflow?.activities ?? []),
  ]
  const definitionsById = new Map<string, ActivityDefinition>()
  for (const node of roots.flatMap(collectActivityDefinitions)) {
    if (node.id) definitionsById.set(node.id, node)
  }

  return pointIds.flatMap((id) => {
    const node = definitionsById.get(id)
    const parameterNames = node?.parameters ? Object.keys(node.parameters) : []
    if (parameterNames.length === 0) return []
    return [
      {
        id,
        name: activityNameMap.get(id) ?? node?.name ?? id,
        parameterNames,
        failedActivityName: findFailedActivityName(id, activities),
      },
    ]
  })
}

function collectActivityDefinitions(node: ActivityDefinition): ActivityDefinition[] {
  const nested: ActivityDefinition[] = [
    ...(node.steps ?? []),
    ...(node.then ?? []),
    ...(node.else ?? []),
    ...(node.loop?.do ?? []),
  ]

  for (const branch of node.branches ?? []) {
    if (typeof branch === 'string') continue
    nested.push(...(Array.isArray(branch) ? branch : [branch]))
  }

  return [node, ...nested.flatMap(collectActivityDefinitions)]
}

function findFailedActivityName(nodeId: string, activities: ExecutionActivity[]): string | undefined {
  const failedActivities = activities
    .map((activity) => ({
      name: 'activity_name' in activity ? activity.activity_name : activity.activity_id,
      status: activity.status,
      timestamp:
        activity.completed_at ??
        activity.started_at ??
        ('created_at' in activity ? activity.created_at : undefined) ??
        '',
    }))
    .filter(({ name, status }) => status === 'failed' && parseCompositeKey(name).baseId === nodeId)

  return failedActivities.sort((a, b) => a.timestamp.localeCompare(b.timestamp)).at(-1)?.name
}

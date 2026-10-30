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

export type RetryInputOverrideDraftResult = Readonly<{
  parsed: Record<string, unknown> | undefined
  error: string | undefined
}>

/** Returns the resolved values that will be sent for retry, with saved overrides applied by parameter key. */
export function getEffectiveRetryInputs(
  resolvedInputs: Record<string, unknown> | null,
  savedOverride: Record<string, unknown> | undefined
): Record<string, unknown> | null {
  if (!resolvedInputs && !savedOverride) return null
  return { ...resolvedInputs, ...savedOverride }
}

function valuesEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right)
}

/** Allowed-parameter JSON shown in the retry editor, with saved overrides applied. */
export function getRetryInputEditorValue(
  resolvedInputs: Record<string, unknown> | null,
  savedOverride: Record<string, unknown> | undefined,
  parameterNames: string[]
): string {
  const effective = getEffectiveRetryInputs(resolvedInputs, savedOverride) ?? {}
  const picked: Record<string, unknown> = {}
  for (const name of parameterNames) {
    if (name in effective) picked[name] = effective[name]
  }
  return JSON.stringify(picked, null, 2)
}

/** Keys that differ from the original resolved inputs, so the retry payload stays a sparse override. */
export function diffRetryInputOverrides(
  resolvedInputs: Record<string, unknown> | null,
  edited: Record<string, unknown>
): Record<string, unknown> | undefined {
  const next: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(edited)) {
    if (!valuesEqual(resolvedInputs?.[key], value)) next[key] = value
  }
  return Object.keys(next).length > 0 ? next : undefined
}

export type RetryInputOverridesState = Readonly<{
  targets: RetryInputOverrideTarget[]
  canEdit: boolean
  isDisabled: boolean
  savedOverrides: Readonly<Record<string, Record<string, unknown>>>
  drafts: Readonly<Record<string, string>>
  errors: Readonly<Record<string, string>>
  editingTargetIds: ReadonlySet<string>
  onEdit: (targetId: string, initialDraft?: string) => void
  onCancel: (targetId: string) => void
  onSave: (targetId: string, overrides: Record<string, unknown> | undefined) => void
  onDraftChange: (
    targetId: string,
    value: string,
    parsed: Record<string, unknown> | undefined,
    error: string | undefined
  ) => void
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
    const { baseId } = parseCompositeKey(id)
    const node = definitionsById.get(baseId)
    const parameterNames = node?.parameters ? Object.keys(node.parameters) : []
    if (parameterNames.length === 0) return []
    return [
      {
        id,
        name: activityNameMap.get(baseId) ?? activityNameMap.get(id) ?? node?.name ?? id,
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
    .filter(
      ({ name, status }) => status === 'failed' && parseCompositeKey(name).baseId === parseCompositeKey(nodeId).baseId
    )

  const exactActivity = failedActivities.find(({ name }) => name === nodeId)
  if (exactActivity) return exactActivity.name

  return failedActivities.sort((a, b) => a.timestamp.localeCompare(b.timestamp)).at(-1)?.name
}

export function parseRetryInputOverrideDraft(
  value: string,
  allowedParameterNames: string[]
): RetryInputOverrideDraftResult {
  let parsedValue: unknown
  try {
    parsedValue = JSON.parse(value)
  } catch {
    return { parsed: undefined, error: 'Enter a valid JSON object.' }
  }

  if (parsedValue === null || typeof parsedValue !== 'object' || Array.isArray(parsedValue)) {
    return { parsed: undefined, error: 'Enter a JSON object of parameter names and values.' }
  }

  const parsed = parsedValue as Record<string, unknown>
  const unknownParameters = Object.keys(parsed).filter((key) => !allowedParameterNames.includes(key))
  if (unknownParameters.length > 0) {
    return {
      parsed: undefined,
      error: `Unknown parameter${unknownParameters.length === 1 ? '' : 's'}: ${unknownParameters.join(', ')}.`,
    }
  }

  return { parsed: Object.keys(parsed).length > 0 ? parsed : undefined, error: undefined }
}

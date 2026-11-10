import { ActivityTypeEnum, EdgeHandleEnum, type Activity } from '@syntara/contracts'

import type { EdgeConnection } from '../../../types/edge'
import { getUpstreamNodeIds } from '../../edgeHelpers'
import type { ValidationContext, ValidationError } from '../types'

// Keep in sync with BUILTIN_SCOPES in backend/src/syntara/workflows/validators/template_expressions.py
const KNOWN_NAMESPACES = new Set(['trigger', 'workflow_context'])
// Scope available only to steps inside a loop body (mirrors the `loop` scope check in the backend validator)
const LOOP_NAMESPACE = 'loop'
const VARIABLE_REF_PATTERN = /\$\{([^}]+)\}/g

type VariableReference = {
  namespace: string
  fullRef: string
}

function parseVariableReference(ref: string): VariableReference | null {
  const trimmed = ref.trim()
  if (!trimmed) return null
  const dotIndex = trimmed.indexOf('.')
  if (dotIndex === -1) return { namespace: trimmed, fullRef: trimmed }
  return { namespace: trimmed.substring(0, dotIndex), fullRef: trimmed }
}

function extractVariableReferences(value: string): VariableReference[] {
  return [...value.matchAll(VARIABLE_REF_PATTERN)]
    .map((m) => parseVariableReference(m[1]))
    .filter(Boolean) as VariableReference[]
}

function collectStringValues(obj: unknown, acc: string[] = []): string[] {
  if (typeof obj === 'string') {
    acc.push(obj)
  } else if (Array.isArray(obj)) {
    for (const item of obj) collectStringValues(item, acc)
  } else if (obj !== null && typeof obj === 'object') {
    for (const val of Object.values(obj)) collectStringValues(val, acc)
  }
  return acc
}

function getWorkflowInputNames(triggers: Activity[] | undefined): Set<string> {
  const names = new Set<string>()
  if (!triggers) return names
  for (const trigger of triggers) {
    const params = trigger.parameters as Record<string, unknown> | undefined
    const inputSchema = params?.input_schema as Record<string, unknown> | undefined
    const properties = inputSchema?.properties as Record<string, unknown> | undefined
    if (properties) {
      for (const key of Object.keys(properties)) {
        names.add(key)
      }
    }
  }
  return names
}

function checkSchemaFieldReference(params: {
  ref: VariableReference
  activity: Activity
  fields: Set<string>
  namespace: string
  suggestionText: string
}): ValidationError | null {
  const { ref, activity, fields, namespace, suggestionText } = params
  const fieldPath = ref.fullRef.substring(ref.namespace.length + 1)
  if (!fieldPath) return null
  const topLevelField = fieldPath.split('.')[0]
  if (fields.has(topLevelField)) return null

  return {
    id: `var-ref-${namespace}-${activity.id}-${fieldPath}`,
    severity: 'error',
    rule: 'variable-references',
    message: `Step "${activity.name ?? activity.id}" references \${${namespace}.${fieldPath}} but "${topLevelField}" is not a defined ${namespace} field`,
    nodeId: activity.id,
    suggestion: suggestionText,
  }
}

function checkNodeReference(
  ref: VariableReference,
  activity: Activity,
  referenceTargetIds: Set<string>,
  upstreamIds: Set<string>
): ValidationError | null {
  const stepName = activity.name ?? activity.id
  if (!referenceTargetIds.has(ref.namespace)) {
    return {
      id: `var-ref-node-${activity.id}-${ref.namespace}`,
      severity: 'error',
      rule: 'variable-references',
      message: `Step "${stepName}" references \${${ref.fullRef}} but node or trigger "${ref.namespace}" does not exist in this workflow`,
      nodeId: activity.id,
      suggestion: 'Check the node ID for typos, or add the referenced node to the workflow',
    }
  }
  if (!upstreamIds.has(ref.namespace)) {
    return {
      id: `var-ref-upstream-${activity.id}-${ref.namespace}`,
      severity: 'error',
      rule: 'variable-references',
      message: `Step "${stepName}" references \${${ref.fullRef}} but node "${ref.namespace}" is not upstream of this step`,
      nodeId: activity.id,
      suggestion: 'Only nodes that execute before this step can provide output data. Check the workflow connections',
    }
  }
  return null
}

type RefContext = {
  schemaFields: Set<string>
  schemaSuggestion: string
  referenceTargetIds: Set<string>
  upstreamIds: Set<string>
  inLoopBody: boolean
}

/**
 * Collects the IDs of every activity that sits inside a loop body: anything reachable from a loop
 * node's `loop` handle, following outgoing edges until the traversal returns to that loop node.
 * Mirrors `_identify_loop_body_nodes` in the backend template-expression validator.
 */
function getLoopBodyNodeIds(activities: Activity[], edges: EdgeConnection[]): Set<string> {
  const bodyIds = new Set<string>()
  const loopIds = activities.filter((a) => a.type === ActivityTypeEnum.LOOP).map((a) => a.id)
  for (const loopId of loopIds) {
    const queue = edges
      .filter((e) => e.source === loopId && e.sourceHandle === EdgeHandleEnum.LOOP)
      .map((e) => e.target)
    const visited = new Set<string>()
    while (queue.length > 0) {
      const nodeId = queue.shift() as string
      if (nodeId === loopId || visited.has(nodeId)) continue
      visited.add(nodeId)
      bodyIds.add(nodeId)
      for (const edge of edges) {
        if (edge.source === nodeId && edge.target !== loopId && !visited.has(edge.target)) queue.push(edge.target)
      }
    }
  }
  return bodyIds
}

function checkLoopScopeReference(
  ref: VariableReference,
  activity: Activity,
  inLoopBody: boolean
): ValidationError | null {
  if (inLoopBody) return null
  return {
    id: `var-ref-loop-scope-${activity.id}`,
    severity: 'error',
    rule: 'variable-references',
    message: `Step "${activity.name ?? activity.id}" references \${${ref.fullRef}} but it is not inside a loop body`,
    nodeId: activity.id,
    suggestion:
      "Only steps connected from a loop's Loop handle can use ${loop.item} and ${loop.index}. Steps on the Done handle can use ${<loop_step_id>.iteration_results} instead",
  }
}

function validateRef(ref: VariableReference, activity: Activity, ctx: RefContext): ValidationError | null {
  if (ref.namespace === 'trigger')
    return checkSchemaFieldReference({
      ref,
      activity,
      fields: ctx.schemaFields,
      namespace: ref.namespace,
      suggestionText: ctx.schemaSuggestion,
    })
  if (KNOWN_NAMESPACES.has(ref.namespace)) return null
  if (ref.namespace === LOOP_NAMESPACE && !ctx.referenceTargetIds.has(LOOP_NAMESPACE))
    return checkLoopScopeReference(ref, activity, ctx.inLoopBody)
  return checkNodeReference(ref, activity, ctx.referenceTargetIds, ctx.upstreamIds)
}

export function validateVariableReferences(
  activities: Activity[],
  edges: EdgeConnection[],
  context?: ValidationContext
): ValidationError[] {
  const errors: ValidationError[] = []
  const seenIds = new Set<string>()
  const activityIds = new Set(activities.map((a) => a.id))
  const triggerIds = new Set(context?.triggers?.map((t) => t.id) ?? [])
  const referenceTargetIds = new Set([...activityIds, ...triggerIds])
  const schemaFields = getWorkflowInputNames(context?.triggers)
  const available = [...schemaFields].sort((a, b) => a.localeCompare(b)).join(', ')
  const schemaSuggestion = available ? `Available fields: ${available}` : 'Define fields in the trigger configuration'
  const loopBodyIds = getLoopBodyNodeIds(activities, edges)

  for (const activity of activities) {
    const paramStrings = collectStringValues(activity.parameters)
    const refs = paramStrings.flatMap(extractVariableReferences)
    if (refs.length === 0) continue

    const needsUpstream = refs.some((ref) => !KNOWN_NAMESPACES.has(ref.namespace))
    const upstreamIds = needsUpstream ? getUpstreamNodeIds(activity.id, edges) : new Set<string>()
    const ctx: RefContext = {
      schemaFields,
      schemaSuggestion,
      referenceTargetIds,
      upstreamIds,
      inLoopBody: loopBodyIds.has(activity.id),
    }

    for (const ref of refs) {
      const error = validateRef(ref, activity, ctx)
      if (error && !seenIds.has(error.id)) {
        seenIds.add(error.id)
        errors.push(error)
      }
    }
  }

  return errors
}

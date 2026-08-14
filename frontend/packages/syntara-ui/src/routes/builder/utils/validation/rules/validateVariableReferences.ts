import type { Activity } from '@syntara/contracts'

import type { EdgeConnection } from '../../../types/edge'
import { getUpstreamNodeIds } from '../../edgeHelpers'
import type { ValidationContext, ValidationError } from '../types'

const KNOWN_NAMESPACES = new Set(['input', 'trigger', 'workflow', 'workflow_context'])
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

function checkSchemaFieldReference(
  ref: VariableReference,
  activity: Activity,
  fields: Set<string>,
  namespace: string,
  suggestionText: string
): ValidationError | null {
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
  activityIds: Set<string>,
  upstreamIds: Set<string>
): ValidationError | null {
  const stepName = activity.name ?? activity.id
  if (!activityIds.has(ref.namespace)) {
    return {
      id: `var-ref-node-${activity.id}-${ref.namespace}`,
      severity: 'error',
      rule: 'variable-references',
      message: `Step "${stepName}" references \${${ref.fullRef}} but node "${ref.namespace}" does not exist in this workflow`,
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
  activityIds: Set<string>
  upstreamIds: Set<string>
}

function validateRef(ref: VariableReference, activity: Activity, ctx: RefContext): ValidationError | null {
  // input.* and trigger.* both resolve to the trigger input_schema fields
  if (ref.namespace === 'input' || ref.namespace === 'trigger')
    return checkSchemaFieldReference(ref, activity, ctx.schemaFields, ref.namespace, ctx.schemaSuggestion)
  if (KNOWN_NAMESPACES.has(ref.namespace)) return null
  return checkNodeReference(ref, activity, ctx.activityIds, ctx.upstreamIds)
}

export function validateVariableReferences(
  activities: Activity[],
  edges: EdgeConnection[],
  context?: ValidationContext
): ValidationError[] {
  const errors: ValidationError[] = []
  const seenIds = new Set<string>()
  const activityIds = new Set(activities.map((a) => a.id))
  const schemaFields = getWorkflowInputNames(context?.triggers)
  const available = [...schemaFields].sort((a, b) => a.localeCompare(b)).join(', ')
  const schemaSuggestion = available ? `Available fields: ${available}` : 'Define fields in the trigger configuration'

  for (const activity of activities) {
    const paramStrings = collectStringValues(activity.parameters)
    const refs = paramStrings.flatMap(extractVariableReferences)
    if (refs.length === 0) continue

    const needsUpstream = refs.some((r) => !KNOWN_NAMESPACES.has(r.namespace))
    const upstreamIds = needsUpstream ? getUpstreamNodeIds(activity.id, edges) : new Set<string>()
    const ctx: RefContext = { schemaFields, schemaSuggestion, activityIds, upstreamIds }

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

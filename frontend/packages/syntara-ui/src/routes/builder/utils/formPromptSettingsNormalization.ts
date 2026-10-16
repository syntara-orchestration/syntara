import { ActivityTypeEnum, EdgeHandleEnum, type Activity } from '@syntara/contracts'

import { prepareFormDefinitionForCommit, safeParseFormDefinition } from '../../../forms'
import type { EdgeConnection } from '../types/edge'

import { handleToV2Port } from './edgeHelpers'

export function buildOutgoingPorts(
  edges: EdgeConnection[],
  resolveSource: (source: string) => string
): Map<string, Set<string>> {
  const outgoingPorts = new Map<string, Set<string>>()
  for (const edge of edges) {
    const fromPort = handleToV2Port(edge.sourceHandle)
    if (!fromPort) continue
    const fromId = resolveSource(edge.source)
    let ports = outgoingPorts.get(fromId)
    if (!ports) {
      ports = new Set()
      outgoingPorts.set(fromId, ports)
    }
    ports.add(fromPort)
  }
  return outgoingPorts
}

export function formPromptHasFallbackEdge(activityId: string, edges: EdgeConnection[]): boolean {
  return edges.some((edge) => {
    if (edge.source !== activityId) return false
    const handle = edge.sourceHandle ?? ''
    const port = handleToV2Port(edge.sourceHandle)
    return port === 'fallback' || handle === EdgeHandleEnum.FALLBACK
  })
}

/** Keys allowed by the backend form_prompt parameterSchema (additionalProperties: false). */
const FORM_PROMPT_PARAMETER_KEYS = new Set([
  'message',
  'form_definition',
  'responder_users',
  'responder_groups',
  'response_window',
  'fallback_decision',
  'submit_label',
  'success_message',
  'timezone',
  'css_override',
])

function sanitizeFormPromptParameters(parameters: Record<string, unknown>): Record<string, unknown> {
  const sanitized: Record<string, unknown> = {}
  for (const key of FORM_PROMPT_PARAMETER_KEYS) {
    if (key in parameters) {
      sanitized[key] = parameters[key]
    }
  }

  const rawDefinition = sanitized.form_definition
  if (rawDefinition !== undefined && rawDefinition !== null) {
    const withFields = rawDefinition as { fields?: unknown }
    if (Array.isArray(withFields.fields)) {
      const prepared = prepareFormDefinitionForCommit(
        rawDefinition as Parameters<typeof prepareFormDefinitionForCommit>[0]
      )
      const parsed = safeParseFormDefinition(prepared)
      if (parsed.success) {
        sanitized.form_definition = parsed.data
      }
    }
  }

  return sanitized
}

/**
 * Normalize form_prompt activities before workflow definition validation/save.
 * Strips UI-only fields (e.g. fallback_behavior) and cross-step keys (e.g. approval
 * ``prompt``) that cause JSON Schema oneOf validation to surface misleading agentic errors.
 */
export function normalizeFormPromptActivityForDefinition(activity: Activity): Activity {
  if (activity.type !== ActivityTypeEnum.FORM_PROMPT) return activity

  const parameters = { ...(activity.parameters ?? {}) } as Record<string, unknown>
  const needsSanitize =
    'fallback_behavior' in parameters || Object.keys(parameters).some((key) => !FORM_PROMPT_PARAMETER_KEYS.has(key))
  if (!needsSanitize) {
    return activity
  }

  return {
    ...activity,
    parameters: sanitizeFormPromptParameters(parameters),
  }
}

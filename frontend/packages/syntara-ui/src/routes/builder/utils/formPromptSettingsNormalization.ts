import { ActivityTypeEnum, EdgeHandleEnum, TriggerTypeEnum, type Activity, type WorkflowAPI } from '@syntara/contracts'

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

/** Compile-time exhaustive against the generated backend parameter contract. */
const FORM_PROMPT_PARAMETER_KEY_SET = {
  message: true,
  form_definition: true,
  response_schema: true,
  responder_users: true,
  responder_groups: true,
  response_window: true,
  fallback_decision: true,
  submit_label: true,
  success_message: true,
} satisfies Record<keyof WorkflowAPI.components['schemas']['FormPromptNodeParameters'], true>

const FORM_PROMPT_PARAMETER_KEYS = new Set(Object.keys(FORM_PROMPT_PARAMETER_KEY_SET))

function sanitizeFormPromptParameters(parameters: Record<string, unknown>): Record<string, unknown> {
  const sanitized: Record<string, unknown> = {}
  for (const key of FORM_PROMPT_PARAMETER_KEYS) {
    if (key in parameters) {
      sanitized[key] = parameters[key]
    }
  }

  delete sanitized.response_schema

  const rawDefinition = sanitized.form_definition
  if (rawDefinition !== undefined && rawDefinition !== null) {
    const withFields = rawDefinition as { fields?: unknown }
    if (Array.isArray(withFields.fields)) {
      const prepared = prepareFormDefinitionForCommit(
        rawDefinition as Parameters<typeof prepareFormDefinitionForCommit>[0]
      )
      const parsed = safeParseFormDefinition(prepared)
      // Always send the prepared snapshot (including invalid include combos) so workflow save
      // validation sees the same shape as verify/run; canonical parse output only when valid.
      sanitized.form_definition = parsed.success ? parsed.data : prepared
    }
  }

  return sanitized
}

/**
 * Normalize form_prompt activities before workflow definition validation/save.
 *
 * The backend form_prompt parameterSchema is `additionalProperties: false`, so any key
 * outside the contract makes validate and save fail outright. Strips UI-only fields
 * (e.g. `fallback_behavior`, mapped forward to `fallback_decision`) and cross-step
 * leftovers from a step that changed type.
 */
export function normalizeFormPromptActivityForDefinition(activity: Activity): Activity {
  if (activity.type !== ActivityTypeEnum.FORM_PROMPT) return activity

  const parameters = { ...(activity.parameters ?? {}) } as Record<string, unknown>
  return {
    ...activity,
    parameters: sanitizeFormPromptParameters(parameters),
  }
}

export function normalizeFormTriggerForDefinition(trigger: Activity): Activity {
  if (trigger.type !== TriggerTypeEnum.FORM_TRIGGER) return trigger
  if (!trigger.parameters || !('response_schema' in trigger.parameters)) return trigger

  const parameters = { ...trigger.parameters }
  delete parameters.response_schema
  return { ...trigger, parameters }
}

import { ActivityTypeEnum, EdgeHandleEnum, type Activity } from '@syntara/contracts'

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

/**
 * Strips UI-only `fallback_behavior` before workflow definition validation/save.
 * Backend form_prompt parameterSchema allows `fallback_decision` only (`additionalProperties: false`).
 */
export function normalizeFormPromptActivityForDefinition(activity: Activity): Activity {
  if (activity.type !== ActivityTypeEnum.FORM_PROMPT) return activity

  const parameters = { ...(activity.parameters ?? {}) } as Record<string, unknown>
  if (!('fallback_behavior' in parameters)) {
    return activity
  }

  const { fallback_behavior: _removed, ...rest } = parameters
  return {
    ...activity,
    parameters: rest,
  }
}

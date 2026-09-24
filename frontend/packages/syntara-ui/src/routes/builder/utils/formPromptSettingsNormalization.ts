import { ActivityTypeEnum, EdgeHandleEnum, type Activity } from '@syntara/contracts'

import type { EdgeConnection } from '../types/edge'

import { handleToV2Port } from './edgeHelpers'
import { formPromptFallbackBehaviorFromDecision } from './formPromptFallbackBehavior'

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
 * Ensures `fallback_behavior` is set when only `fallback_decision` is present.
 * Does not override on-failure settings or infer routing from canvas edges alone.
 */
export function normalizeFormPromptActivityForDefinition(activity: Activity): Activity {
  if (activity.type !== ActivityTypeEnum.FORM_PROMPT) return activity

  const parameters = { ...(activity.parameters ?? {}) } as Record<string, unknown>
  if (parameters.fallback_behavior !== undefined) {
    return activity
  }
  if (parameters.fallback_decision === undefined) {
    return activity
  }

  return {
    ...activity,
    parameters: {
      ...parameters,
      fallback_behavior: formPromptFallbackBehaviorFromDecision(parameters.fallback_decision as 'submit' | 'fallback'),
    },
  }
}

import type { WorkflowAPI } from '@syntara/contracts'

type NodeKindDenial = Pick<WorkflowAPI.components['schemas']['BlockedStepType'], 'kind' | 'label' | 'reason'>

function denialBody(error: unknown, visited = new Set<object>()): Record<string, unknown> | undefined {
  if (!error || typeof error !== 'object' || visited.has(error)) return undefined
  visited.add(error)
  if ('code' in error && error.code === 'NODE_KIND_WRITE_DENIED') return error
  for (const key of ['cause', 'data']) {
    if (key in error) {
      const body = denialBody(Reflect.get(error, key), visited)
      if (body) return body
    }
  }
  return undefined
}

export function isNodeKindWriteDeniedError(error: unknown): boolean {
  return denialBody(error) !== undefined
}

export function extractNodeKindDenials(error: unknown): NodeKindDenial[] {
  const blocked = denialBody(error)?.blocked_step_types
  if (!Array.isArray(blocked)) return []
  return blocked.filter(
    (item: unknown): item is NodeKindDenial =>
      !!item &&
      typeof item === 'object' &&
      'kind' in item &&
      typeof item.kind === 'string' &&
      'label' in item &&
      typeof item.label === 'string' &&
      'reason' in item &&
      (item.reason === 'explicit_deny' || item.reason === 'no_matching_allow')
  )
}

export function getNodeKindWriteDeniedMessage(error: unknown): string | undefined {
  const body = denialBody(error)
  if (!body) return undefined
  if (typeof body.detail === 'string' && body.detail) return body.detail
  const blocked = extractNodeKindDenials(error)
  const names = blocked.map(
    ({ label, reason }) => `${label} (${reason === 'no_matching_allow' ? 'no matching write grant' : 'write denied'})`
  )
  return names.length ? `Step types not allowed: ${names.join('; ')}.` : 'Step types not allowed.'
}

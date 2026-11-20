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
      item.kind.trim().length > 0 &&
      'label' in item &&
      typeof item.label === 'string' &&
      item.label.trim().length > 0 &&
      'reason' in item &&
      (item.reason === 'explicit_deny' || item.reason === 'no_matching_allow')
  )
}

export function formatStepTypeWriteDenial(blockedStepTypes: readonly { label: string }[], project = false): string {
  const labels = blockedStepTypes.map(({ label }) => label).join(', ')
  const subject = project ? 'This project includes workflows with' : 'This workflow includes'
  return `${subject} ${labels} steps, but your assigned policies don't allow you to write them.`
}

export function getNodeKindWriteDeniedMessage(error: unknown, project = false): string | undefined {
  const blocked = extractNodeKindDenials(error)
  return blocked.length ? formatStepTypeWriteDenial(blocked, project) : undefined
}

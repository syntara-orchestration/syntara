import type { NodeKind } from '../../hooks/useNodeKindsQuery'

/** A raw run definition as stored on the execution and sent to `POST /workflows`. */
export type RawWorkflowDefinition = Record<string, unknown>

/** One step type the caller may not write, named by its own label (never the policy). */
export type BlockedForkStepType = { kind: string; label: string }

/**
 * A fork waiting for the user to accept leaving out the step types they may not
 * write. `losesAllTriggers` is true when the run has triggers and every one of
 * them is of a blocked type, so the fork would have none.
 */
export type BlockedFork = { labels: string[]; losesAllTriggers: boolean }

type RawStep = Record<string, unknown>

function rawSteps(definition: RawWorkflowDefinition, key: 'nodes' | 'triggers'): RawStep[] {
  const steps = definition[key]
  return Array.isArray(steps)
    ? steps.filter((step: unknown): step is RawStep => typeof step === 'object' && step !== null)
    : []
}

function stepType(step: RawStep): string | undefined {
  return typeof step.type === 'string' ? step.type : undefined
}

/**
 * Step types in the raw `definition` the caller may not write, unique and in the
 * order they first appear (nodes, then triggers). Kinds with no verdict are allowed.
 */
export function blockedForkStepTypes(
  definition: RawWorkflowDefinition,
  nodeKindByKind: ReadonlyMap<string, NodeKind>
): BlockedForkStepType[] {
  const blocked = new Map<string, BlockedForkStepType>()
  for (const step of [...rawSteps(definition, 'nodes'), ...rawSteps(definition, 'triggers')]) {
    const type = stepType(step)
    const verdict = type ? nodeKindByKind.get(type) : undefined
    if (!verdict || verdict.can_write || blocked.has(verdict.kind)) continue
    blocked.set(verdict.kind, { kind: verdict.kind, label: verdict.blocked_by?.label ?? verdict.kind })
  }
  return [...blocked.values()]
}

/** Whether the definition has triggers and removing `kinds` would remove all of them. */
export function forkLosesAllTriggers(definition: RawWorkflowDefinition, kinds: Iterable<string>): boolean {
  const removed = new Set(kinds)
  const triggers = rawSteps(definition, 'triggers')
  return triggers.length > 0 && triggers.every((trigger) => removed.has(stepType(trigger) ?? ''))
}

/**
 * The raw `definition` without the nodes and triggers of the given step types
 * and without the edges whose `from` or `to` is one of them. Node positions live
 * on the nodes, so they go with them. Other keys are kept. Does not mutate
 * `definition`.
 */
export function withoutForkStepTypes(
  definition: RawWorkflowDefinition,
  kinds: Iterable<string>
): RawWorkflowDefinition {
  const removedKinds = new Set(kinds)
  const removedIds = new Set<string>()
  const keep = (step: RawStep): boolean => {
    const type = stepType(step)
    if (!type || !removedKinds.has(type)) return true
    if (typeof step.id === 'string') removedIds.add(step.id)
    return false
  }

  const result: RawWorkflowDefinition = { ...definition }
  if (Array.isArray(definition.nodes)) result.nodes = rawSteps(definition, 'nodes').filter(keep)
  if (Array.isArray(definition.triggers)) result.triggers = rawSteps(definition, 'triggers').filter(keep)
  if (Array.isArray(definition.edges)) {
    result.edges = definition.edges.filter((edge: unknown) => {
      if (typeof edge !== 'object' || edge === null) return true
      const from: unknown = Reflect.get(edge, 'from')
      const to: unknown = Reflect.get(edge, 'to')
      return !(typeof from === 'string' && removedIds.has(from)) && !(typeof to === 'string' && removedIds.has(to))
    })
  }
  return result
}

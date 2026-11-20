import { ActivityTypeEnum, EdgeHandleEnum } from '@syntara/contracts'

import { buildSwitchCasePort, isValidSwitchPort } from './switchCaseHelpers'

/**
 * Utilities for detecting if a workflow step may not always execute
 * due to being inside a conditional, switch, approval, or loop construct.
 */

type Activity = {
  id: string
  type: string
  parameters?: Record<string, unknown>
}

type Edge = {
  source: string
  target: string
  sourceHandle?: string | null
}

type Graph = Map<string, Edge[]>
type GuaranteeContext = {
  stepId: string
  graph: Graph
  activitiesById: ReadonlyMap<string, Activity>
  memo: Map<string, boolean>
  visiting: Set<string>
}

const BRANCH_NODE_TYPES: ReadonlySet<string> = new Set([
  ActivityTypeEnum.CONDITION,
  ActivityTypeEnum.SWITCH,
  ActivityTypeEnum.APPROVAL,
])
const LOOP_NODE_TYPES = new Set(['loop', 'loop_each'])
const LOOP_DONE_HANDLE = EdgeHandleEnum.DONE

/**
 * Extract step ID from a template expression like "${step.field}" or "${step}".
 * Returns null if the expression doesn't reference a step.
 */
export function extractStepIdFromExpression(expression: string): string | null {
  const match = expression.match(/^\$\{([^.}]+)/)
  return match ? match[1] : null
}

function buildGraph(edges: Edge[]): Graph {
  const graph = new Map<string, Edge[]>()
  for (const edge of edges) {
    const outgoing = graph.get(edge.source) ?? []
    outgoing.push(edge)
    graph.set(edge.source, outgoing)
  }
  return graph
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function canReachStep(startId: string, stepId: string, graph: Graph): boolean {
  const visited = new Set<string>()
  const queue = [startId]
  let cursor = 0

  while (cursor < queue.length) {
    const currentId = queue[cursor]
    cursor += 1
    if (!currentId || visited.has(currentId)) continue
    if (currentId === stepId) return true
    visited.add(currentId)
    for (const edge of graph.get(currentId) ?? []) queue.push(edge.target)
  }

  return false
}

function getPossibleBranchHandles(activity: Activity): string[] {
  switch (activity.type) {
    case ActivityTypeEnum.CONDITION:
      return [EdgeHandleEnum.TRUE, EdgeHandleEnum.FALSE]
    case ActivityTypeEnum.APPROVAL:
      return [EdgeHandleEnum.APPROVED, EdgeHandleEnum.REJECTED]
    case ActivityTypeEnum.SWITCH: {
      const configuredCases = activity.parameters?.['cases']
      const cases: unknown[] = Array.isArray(configuredCases) ? configuredCases : []
      const caseHandles = cases.map((candidate, index) => {
        if (isRecord(candidate) && isValidSwitchPort(candidate['port'])) return candidate['port']
        return buildSwitchCasePort(index)
      })
      const configuredDefault = activity.parameters?.['default_port']
      const defaultHandle = isValidSwitchPort(configuredDefault) ? configuredDefault : EdgeHandleEnum.DEFAULT
      return [...caseHandles, defaultHandle]
    }
    default:
      return []
  }
}

function getGuaranteedEdges(activity: Activity | undefined, outgoing: Edge[]): Edge[][] {
  if (LOOP_NODE_TYPES.has(activity?.type ?? '')) {
    const doneEdges = outgoing.filter((edge) => edge.sourceHandle === LOOP_DONE_HANDLE)
    return doneEdges.length > 0 ? [doneEdges] : []
  }
  if (activity && BRANCH_NODE_TYPES.has(activity.type)) {
    return getPossibleBranchHandles(activity).map((handle) => outgoing.filter((edge) => edge.sourceHandle === handle))
  }
  return [outgoing]
}

function stepIsGuaranteedFrom(currentId: string, context: GuaranteeContext): boolean {
  const { stepId, graph, activitiesById, memo, visiting } = context
  if (currentId === stepId) return true
  const cached = memo.get(currentId)
  if (cached !== undefined) return cached
  if (visiting.has(currentId)) return false

  const outgoing = graph.get(currentId) ?? []
  if (outgoing.length === 0) {
    memo.set(currentId, false)
    return false
  }

  visiting.add(currentId)
  const branchGroups = getGuaranteedEdges(activitiesById.get(currentId), outgoing)
  const isGuaranteed =
    branchGroups.length > 0 &&
    branchGroups.every((branch) => branch.some((edge) => stepIsGuaranteedFrom(edge.target, context)))
  visiting.delete(currentId)
  memo.set(currentId, isGuaranteed)
  return isGuaranteed
}

/**
 * Determine whether a step can be skipped by choosing another workflow branch
 * or by completing a loop without entering its body.
 *
 * Regular nodes schedule all outgoing edges, so one successor path that
 * guarantees the target is enough. Condition, switch, and approval nodes select
 * one port, so every defined port—including unconnected ports—must guarantee
 * the target. Loop bodies are optional; only the `done` port is guaranteed to run.
 */
export function isStepConditional(
  stepId: string,
  activities: Activity[],
  edges: Edge[],
  triggerIds: string[]
): boolean {
  const graph = buildGraph(edges)
  const activitiesById = new Map(activities.map((activity) => [activity.id, activity]))

  return triggerIds.some((triggerId) => {
    if (!canReachStep(triggerId, stepId, graph)) return false
    const context: GuaranteeContext = { stepId, graph, activitiesById, memo: new Map(), visiting: new Set() }
    return !stepIsGuaranteedFrom(triggerId, context)
  })
}

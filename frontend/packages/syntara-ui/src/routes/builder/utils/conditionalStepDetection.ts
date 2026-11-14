/**
 * Utilities for detecting if a workflow step may not always execute
 * due to being inside a conditional, switch, approval, or loop construct.
 */

type Activity = {
  id: string
  type: string
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
  activityTypes: ReadonlyMap<string, string>
  memo: Map<string, boolean>
  visiting: Set<string>
}

const BRANCH_NODE_TYPES = new Set(['condition', 'switch', 'approval'])
const LOOP_NODE_TYPES = new Set(['loop', 'loop_each'])
const LOOP_DONE_HANDLE = 'done'

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

function groupedBranchEdges(edges: Edge[]): Edge[][] {
  const branches = new Map<string, Edge[]>()
  for (const edge of edges) {
    const branchKey = edge.sourceHandle ?? ''
    const branch = branches.get(branchKey) ?? []
    branch.push(edge)
    branches.set(branchKey, branch)
  }
  return [...branches.values()]
}

function getGuaranteedEdges(nodeType: string | undefined, outgoing: Edge[]): Edge[][] {
  if (LOOP_NODE_TYPES.has(nodeType ?? '')) {
    const doneEdges = outgoing.filter((edge) => edge.sourceHandle === LOOP_DONE_HANDLE)
    return doneEdges.length > 0 ? [doneEdges] : []
  }
  if (BRANCH_NODE_TYPES.has(nodeType ?? '')) return groupedBranchEdges(outgoing)
  return [outgoing]
}

function stepIsGuaranteedFrom(currentId: string, context: GuaranteeContext): boolean {
  const { stepId, graph, activityTypes, memo, visiting } = context
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
  const branchGroups = getGuaranteedEdges(activityTypes.get(currentId), outgoing)
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
 * one port, so every port must guarantee the target. Loop bodies are optional;
 * only the `done` port is guaranteed to run.
 */
export function isStepConditional(
  stepId: string,
  activities: Activity[],
  edges: Edge[],
  triggerIds: string[]
): boolean {
  const graph = buildGraph(edges)
  const activityTypes = new Map(activities.map((activity) => [activity.id, activity.type]))

  return triggerIds.some((triggerId) => {
    if (!canReachStep(triggerId, stepId, graph)) return false
    const context: GuaranteeContext = { stepId, graph, activityTypes, memo: new Map(), visiting: new Set() }
    return !stepIsGuaranteedFrom(triggerId, context)
  })
}

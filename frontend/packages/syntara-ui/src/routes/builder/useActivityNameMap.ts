import { useMemo } from 'react'

import { useActivities, useTriggers } from '../../stores/workflowStoreSelectors'
import type { ActivityState } from '../workflows/execution/types'
import { parseCompositeKey } from '../workflows/execution/utils/activityState'

import type { ActivityOrderItem } from './ExecutionActivityTable'

type ActivityLike = {
  id?: string
  name?: string | null
  type?: string
  branches?: (ActivityLike[] | ActivityLike | string)[]
  steps?: ActivityLike[]
  then?: ActivityLike[]
  else?: ActivityLike[]
  loop?: { do?: ActivityLike[] }
  converge?: { branches?: string[] }
}

export type WorkflowDefEdge = { from: string; to: string; from_port?: string; to_port?: string }

export type WorkflowDefShape = {
  workflow?: { activities?: ActivityLike[] }
  /** v2 format stores nodes at top level */
  nodes?: ActivityLike[]
  edges?: Array<WorkflowDefEdge | Record<string, unknown>>
}

const CHILD_KEYS: (keyof ActivityLike)[] = ['steps', 'then', 'else']

function normalizeBranches(branches: (ActivityLike[] | ActivityLike | string)[]): ActivityLike[][] {
  return branches
    .filter((b): b is ActivityLike[] | ActivityLike => typeof b !== 'string')
    .map((b) => (Array.isArray(b) ? b : [b]))
}

function collectNamesFromActivityList(
  acts: ActivityLike[],
  nameMap: Map<string, string>,
  typeMap: Map<string, string>
): void {
  for (const act of acts) {
    collectNamesFromActivity(act, nameMap, typeMap)
  }
}

function collectNamesFromActivity(act: ActivityLike, nameMap: Map<string, string>, typeMap: Map<string, string>): void {
  if (act.id && act.name) nameMap.set(act.id, act.name)
  if (act.id && act.type) typeMap.set(act.id, act.type)

  if (act.branches) {
    for (const branch of normalizeBranches(act.branches)) {
      collectNamesFromActivityList(branch, nameMap, typeMap)
    }
  }

  for (const key of CHILD_KEYS) {
    const children = act[key]
    if (Array.isArray(children)) {
      collectNamesFromActivityList(children as ActivityLike[], nameMap, typeMap)
    }
  }

  if (act.loop?.do) {
    collectNamesFromActivityList(act.loop.do, nameMap, typeMap)
  }
}

function buildNameMap(activities: ActivityLike[] | undefined): {
  nameMap: Map<string, string>
  typeMap: Map<string, string>
} {
  const nameMap = new Map<string, string>()
  const typeMap = new Map<string, string>()
  if (!activities) return { nameMap, typeMap }
  collectNamesFromActivityList(activities, nameMap, typeMap)
  return { nameMap, typeMap }
}

function buildStoreNameMap(
  activities: Array<{ id?: string; name?: string; type?: string }>,
  triggers: Array<{ id?: string; name?: string; type?: string }>
): { nameMap: Map<string, string>; typeMap: Map<string, string> } {
  const nameMap = new Map<string, string>()
  const typeMap = new Map<string, string>()
  for (const act of activities) {
    if (act.id && act.name) nameMap.set(act.id, act.name)
    if (act.id && act.type) typeMap.set(act.id, act.type)
  }
  for (const trigger of triggers) {
    if (trigger.id && trigger.name) nameMap.set(trigger.id, trigger.name)
    if (trigger.id && trigger.type) typeMap.set(trigger.id, trigger.type)
  }
  return { nameMap, typeMap }
}

function buildDefinitionNameMap(def: WorkflowDefShape | null | undefined): {
  nameMap: Map<string, string>
  typeMap: Map<string, string>
} {
  const fromActivities = buildNameMap(def?.workflow?.activities)
  const fromNodes = buildNameMap(def?.nodes)
  if (fromNodes.nameMap.size === 0) return fromActivities
  const mergedNames = new Map(fromActivities.nameMap)
  const mergedTypes = new Map(fromActivities.typeMap)
  for (const [id, name] of fromNodes.nameMap) {
    mergedNames.set(id, name)
  }
  for (const [id, type] of fromNodes.typeMap) {
    mergedTypes.set(id, type)
  }
  return { nameMap: mergedNames, typeMap: mergedTypes }
}

function compareTimestamps(a: string | null | undefined, b: string | null | undefined): number {
  if (a && b) {
    if (a < b) return -1
    if (a > b) return 1
    return 0
  }
  if (a) return -1
  if (b) return 1
  return 0
}

function compareByStartedAt(
  aId: string,
  bId: string,
  activityStates: Map<string, ActivityState>,
  fallback = 0
): number {
  const result = compareTimestamps(activityStates.get(aId)?.startedAt, activityStates.get(bId)?.startedAt)
  return result !== 0 ? result : fallback
}

function sortIterationItems(items: ActivityOrderItem[]): ActivityOrderItem[] {
  return [...items].sort((a, b) => (parseCompositeKey(a.id).iteration ?? 0) - (parseCompositeKey(b.id).iteration ?? 0))
}

function isWorkflowDefEdge(edge: WorkflowDefEdge | Record<string, unknown>): edge is WorkflowDefEdge {
  return typeof (edge as WorkflowDefEdge).from === 'string' && typeof (edge as WorkflowDefEdge).to === 'string'
}

function buildAdjacencyGraph(
  edges: Array<WorkflowDefEdge | Record<string, unknown>>,
  nodeIds: Set<string>
): { adjacencyList: Map<string, string[]>; inDegree: Map<string, number> } {
  const adjacencyList = new Map<string, string[]>()
  const inDegree = new Map<string, number>()

  for (const id of nodeIds) {
    adjacencyList.set(id, [])
    inDegree.set(id, 0)
  }

  for (const edge of edges) {
    if (!isWorkflowDefEdge(edge)) continue
    if (edge.to_port === 'iterate') continue
    if (!nodeIds.has(edge.from) || !nodeIds.has(edge.to) || edge.from === edge.to) continue

    const neighbors = adjacencyList.get(edge.from)
    if (!neighbors) continue
    if (!neighbors.includes(edge.to)) {
      neighbors.push(edge.to)
      inDegree.set(edge.to, (inDegree.get(edge.to) ?? 0) + 1)
    }
  }

  return { adjacencyList, inDegree }
}

function topoSortIds(
  edges: Array<WorkflowDefEdge | Record<string, unknown>>,
  nodeIds: Set<string>,
  activityStates: Map<string, ActivityState>
): string[] {
  const { adjacencyList, inDegree } = buildAdjacencyGraph(edges, nodeIds)

  const queue: string[] = []
  const sortedIds: string[] = []

  for (const [id, degree] of inDegree) {
    if (degree === 0) queue.push(id)
  }

  while (queue.length > 0) {
    queue.sort((a, b) => compareByStartedAt(a, b, activityStates, a.localeCompare(b, 'en')))
    const current = queue.shift()
    if (current === undefined) break
    sortedIds.push(current)

    for (const neighbor of adjacencyList.get(current) ?? []) {
      const newDegree = (inDegree.get(neighbor) ?? 0) - 1
      inDegree.set(neighbor, newDegree)
      if (newDegree === 0) queue.push(neighbor)
    }
  }

  return sortedIds
}

/**
 * Topological sort of activity IDs using Kahn's algorithm on workflow definition edges.
 * Groups loop iterations after their base activity and uses startedAt as a tiebreaker
 * for nodes at the same topological level.
 */
export function sortActivityOrder(
  items: ActivityOrderItem[],
  edges: Array<WorkflowDefEdge | Record<string, unknown>> | undefined,
  activityStates: Map<string, ActivityState>
): ActivityOrderItem[] {
  if (items.length <= 1) return items

  const baseItems: ActivityOrderItem[] = []
  const iterationItems = new Map<string, ActivityOrderItem[]>()

  for (const item of items) {
    const { baseId, iteration } = parseCompositeKey(item.id)
    if (iteration != null) {
      const list = iterationItems.get(baseId) ?? []
      list.push(item)
      iterationItems.set(baseId, list)
    } else {
      baseItems.push(item)
    }
  }

  let sortedBaseItems: ActivityOrderItem[]

  if (edges && edges.length > 0) {
    const nodeIds = new Set(baseItems.map((item) => item.id))
    const sortedIds = topoSortIds(edges, nodeIds, activityStates)

    const sortedIdSet = new Set(sortedIds)
    const remaining = baseItems.filter((item) => !sortedIdSet.has(item.id))
    remaining.sort((a, b) => compareByStartedAt(a.id, b.id, activityStates))

    const itemMap = new Map(baseItems.map((item) => [item.id, item]))
    sortedBaseItems = [
      ...sortedIds.map((id) => itemMap.get(id)).filter((item): item is ActivityOrderItem => item != null),
      ...remaining,
    ]
  } else {
    sortedBaseItems = [...baseItems].sort((a, b) => compareByStartedAt(a.id, b.id, activityStates))
  }

  const result: ActivityOrderItem[] = []
  for (const item of sortedBaseItems) {
    result.push(item)
    const iterations = iterationItems.get(item.id)
    if (iterations) result.push(...sortIterationItems(iterations))
  }

  for (const [baseId, iterations] of iterationItems) {
    if (!sortedBaseItems.some((item) => item.id === baseId)) {
      result.push(...sortIterationItems(iterations))
    }
  }

  return result
}

export function useActivityNameMap(
  workflowDefinition: WorkflowDefShape | null | undefined,
  activityStates: Map<string, ActivityState>
) {
  const storeActivities = useActivities()
  const storeTriggers = useTriggers()

  const { nameMap, typeMap } = useMemo(() => {
    const hasStoreData = (storeActivities && storeActivities.length > 0) || (storeTriggers && storeTriggers.length > 0)
    if (hasStoreData) {
      return buildStoreNameMap(storeActivities ?? [], storeTriggers ?? [])
    }
    return buildDefinitionNameMap(workflowDefinition)
  }, [storeActivities, storeTriggers, workflowDefinition])

  const activityOrder = useMemo<ActivityOrderItem[]>(() => {
    const unsorted = Array.from(activityStates.keys()).map((id) => {
      const { baseId, iteration } = parseCompositeKey(id)
      const baseName = nameMap.get(baseId)
      const effectiveIteration = iteration ?? activityStates.get(id)?.iteration
      let name: string | undefined
      if (effectiveIteration != null && baseName) {
        name = `${baseName} (Iteration ${effectiveIteration + 1})`
      } else {
        name = nameMap.get(id)
      }
      return { id, name, type: typeMap.get(baseId) ?? typeMap.get(id) }
    })

    return sortActivityOrder(unsorted, workflowDefinition?.edges, activityStates)
  }, [activityStates, nameMap, typeMap, workflowDefinition])

  return { nameMap, activityOrder }
}

export function resolveNodeName(nameMap: Map<string, string>, nodeId?: string | null): string | undefined {
  if (!nodeId) return undefined
  return nameMap.get(nodeId) ?? nodeId
}

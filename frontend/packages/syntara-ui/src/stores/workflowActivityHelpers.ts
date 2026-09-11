import { ActivityTypeEnum, EdgeHandleEnum } from '@syntara/contracts'

import type { EdgeConnection } from '../routes/builder/types/edge'
import { isSwitchCasePort } from '../routes/builder/utils/switchCaseHelpers'

import type { Activity } from './workflowStoreTypes'

/**
 * Collect all activity IDs from a flat list.
 * In v2 all nodes are top-level so this is a simple map.
 */
export function collectAllActivityIds(activities: Activity[]): Set<string> {
  return new Set(activities.map((a) => a.id))
}

/**
 * Find an activity by ID in a flat list of activities (v2 — no nesting).
 */
export function findActivityById(activities: Activity[], targetId: string): Activity | null {
  return activities.find((a) => a.id === targetId) ?? null
}

/**
 * Remove an activity from a flat list (v2 — no nested structures to clean up).
 */
export function removeActivityFromList(activities: Activity[], activityId: string): Activity[] {
  return activities.filter((a) => a.id !== activityId)
}

/**
 * Walk a flat activity list, applying `mapper` to the single activity
 * whose id matches `activityId`.  Both updateActivityInList and
 * replaceActivityInList delegate here so the logic lives in one place.
 *
 * In v2, nodes are flat — no nested traversal needed.
 */
function mapActivityInList(
  activities: Activity[],
  activityId: string,
  mapper: (activity: Activity) => Activity
): Activity[] {
  return activities.map((activity) => (activity.id === activityId ? mapper(activity) : activity))
}

/** Merge `updates` into the matching activity (preserves existing fields). */
export function updateActivityInList(
  activities: Activity[],
  activityId: string,
  updates: Partial<Activity>
): Activity[] {
  return mapActivityInList(activities, activityId, (activity) => ({ ...activity, ...updates }) as Activity)
}

/**
 * Fully replace the matching activity, discarding all type-specific fields from
 * the old one.  The replacement is stored with `id` set to `activityId` so
 * position-dependent consumers (edges, converge nodes) continue to work.
 */
export function replaceActivityInList(activities: Activity[], activityId: string, newActivity: Activity): Activity[] {
  return mapActivityInList(activities, activityId, () => ({ ...newActivity, id: activityId }) as Activity)
}

/**
 * Returns the set of valid outgoing sourceHandle values for an activity type.
 * Used by replaceActivity to prune edges that become incompatible after a type change.
 */
export function getValidSourceHandles(activityType: Activity['type']): Set<string> {
  switch (activityType) {
    case ActivityTypeEnum.CONDITION:
      return new Set([EdgeHandleEnum.TRUE, EdgeHandleEnum.FALSE])
    case ActivityTypeEnum.LOOP:
      return new Set([EdgeHandleEnum.LOOP, EdgeHandleEnum.DONE])
    case ActivityTypeEnum.APPROVAL:
      return new Set([EdgeHandleEnum.APPROVED, EdgeHandleEnum.REJECTED])
    case ActivityTypeEnum.SWITCH:
      // Returns only the static DEFAULT handle. Dynamic case_N handles are
      // managed by SwitchNodeDetails.handleSubmit during edit-mode updates.
      return new Set([EdgeHandleEnum.DEFAULT])
    default:
      // All other v2 node types (script, http_request, agentic, aap_job_template, converge)
      // use the standard source handle.
      return new Set([EdgeHandleEnum.SOURCE])
  }
}

/**
 * Reorder activities based on edge connections using topological sort.
 * In v2 all nodes are top-level (flat list), so this sorts the entire list.
 */
export function reorderActivities(activities: Activity[], edges: EdgeConnection[]): Activity[] {
  const topLevelActivityIds = new Set(activities.map((a) => a.id))

  // Build adjacency list and in-degree map from edges
  const adjacencyList = new Map<string, string[]>()
  const inDegree = new Map<string, number>()

  // Initialize all top-level activity nodes
  topLevelActivityIds.forEach((id) => {
    adjacencyList.set(id, [])
    inDegree.set(id, 0)
  })

  // Build graph from edges
  // Only consider sequential edges (not structural edges like loop bodies or condition branches)
  edges.forEach((edge) => {
    const isSwitchBranchEdge = edge.sourceHandle === EdgeHandleEnum.DEFAULT || isSwitchCasePort(edge.sourceHandle)
    const isBranchEdge =
      edge.sourceHandle === EdgeHandleEnum.LOOP ||
      edge.sourceHandle === EdgeHandleEnum.TRUE ||
      edge.sourceHandle === EdgeHandleEnum.FALSE ||
      edge.sourceHandle === EdgeHandleEnum.APPROVED ||
      edge.sourceHandle === EdgeHandleEnum.REJECTED ||
      isSwitchBranchEdge
    const isLoopBackEdge = edge.targetHandle === EdgeHandleEnum.END
    const isSequentialEdge = !isBranchEdge && !isLoopBackEdge

    if (!isSequentialEdge) {
      return
    }

    // v2: all nodes are top-level, so source/target map directly
    const { source: mappedSource, target: mappedTarget } = edge

    // Only add edge if both source and target are known activities and they're different
    if (
      topLevelActivityIds.has(mappedSource) &&
      topLevelActivityIds.has(mappedTarget) &&
      mappedSource !== mappedTarget
    ) {
      const neighbors = adjacencyList.get(mappedSource) ?? []
      // Avoid duplicate edges
      if (!neighbors.includes(mappedTarget)) {
        neighbors.push(mappedTarget)
        adjacencyList.set(mappedSource, neighbors)
        inDegree.set(mappedTarget, (inDegree.get(mappedTarget) ?? 0) + 1)
      }
    }
  })

  // Perform topological sort using Kahn's algorithm
  const queue: string[] = []
  const sortedIds: string[] = []

  // Start with nodes that have no incoming edges
  inDegree.forEach((degree, id) => {
    if (degree === 0) {
      queue.push(id)
    }
  })

  // Process nodes in topological order
  while (queue.length > 0) {
    // Sort queue to ensure deterministic ordering when there are multiple valid orders
    queue.sort((a, b) => a.localeCompare(b, 'en'))
    const current = queue[0]
    queue.shift()
    sortedIds.push(current)

    const neighbors = adjacencyList.get(current) ?? []
    neighbors.forEach((neighbor) => {
      const newDegree = (inDegree.get(neighbor) ?? 0) - 1
      inDegree.set(neighbor, newDegree)
      if (newDegree === 0) {
        queue.push(neighbor)
      }
    })
  }

  // If sortedIds doesn't contain all top-level activities, add remaining ones
  const sortedIdsSet = new Set(sortedIds)
  const remainingActivities = activities.filter((a) => !sortedIdsSet.has(a.id))

  // Rebuild activities array in topological order - only reordering top-level activities
  const reorderedActivities: Activity[] = []

  sortedIds.forEach((id) => {
    const activity = activities.find((a) => a.id === id)
    if (activity) {
      reorderedActivities.push(activity)
    }
  })

  // IMPORTANT: Always preserve all nodes even if they have no connections yet
  remainingActivities.forEach((activity) => {
    reorderedActivities.push(activity)
  })

  // Safety check: Ensure ALL activities from the input are present in the output
  activities.forEach((activity) => {
    if (!reorderedActivities.some((a) => a.id === activity.id)) {
      reorderedActivities.push(activity)
    }
  })

  return reorderedActivities
}

export function remapSwitchEdges(
  edges: EdgeConnection[],
  nodeId: string,
  portMapping: Map<string, string>
): EdgeConnection[] {
  return edges
    .map((edge) => {
      if (edge.source !== nodeId) return edge
      const handle = edge.sourceHandle
      if (!handle || !isSwitchCasePort(handle)) return edge
      const newHandle = portMapping.get(handle)
      return newHandle ? { ...edge, sourceHandle: newHandle } : null
    })
    .filter((edge): edge is NonNullable<typeof edge> => edge !== null)
}

import type { Activity } from '@syntara/contracts'

import type { EdgeConnection } from '../../../types/edge'
import type { ValidationError } from '../types'

/**
 * Validates that all nodes are connected to the workflow graph.
 *
 * A node is considered "dangling" if it has no incoming or outgoing edges.
 *
 * Note: In the new architecture, parallel containers don't exist in the builder format,
 * so all activities are validated equally.
 */
export function validateNoDanglingNodes(activities: Activity[], edges: EdgeConnection[]): ValidationError[] {
  const errors: ValidationError[] = []

  // Build adjacency map for graph traversal
  const adjacencyMap = new Map<string, Set<string>>()
  edges.forEach((edge) => {
    let set = adjacencyMap.get(edge.source)
    if (!set) {
      set = new Set()
      adjacencyMap.set(edge.source, set)
    }
    set.add(edge.target)
  })

  // Also build reverse adjacency map to check for incoming edges
  const reverseAdjacencyMap = new Map<string, Set<string>>()
  edges.forEach((edge) => {
    let set = reverseAdjacencyMap.get(edge.target)
    if (!set) {
      set = new Set()
      reverseAdjacencyMap.set(edge.target, set)
    }
    set.add(edge.source)
  })

  const entryNodes = activities
    .map((a) => a.id)
    .filter((id) => !reverseAdjacencyMap.has(id) || (reverseAdjacencyMap.get(id)?.size ?? 0) === 0)

  // BFS traversal from all entry nodes
  const queue = [...entryNodes]
  const visited = new Set<string>()

  while (queue.length > 0) {
    const nodeId = queue[0]
    queue.shift()
    if (visited.has(nodeId)) continue
    visited.add(nodeId)

    const neighbors = adjacencyMap.get(nodeId) ?? new Set()
    neighbors.forEach((neighbor) => {
      if (!visited.has(neighbor)) {
        queue.push(neighbor)
      }
    })
  }

  // Check each activity
  for (const activity of activities) {
    // A node is dangling if it has NO connections (neither incoming nor outgoing)
    const hasIncomingEdges =
      reverseAdjacencyMap.has(activity.id) && (reverseAdjacencyMap.get(activity.id)?.size ?? 0) > 0
    const hasOutgoingEdges = adjacencyMap.has(activity.id) && (adjacencyMap.get(activity.id)?.size ?? 0) > 0

    if (!hasIncomingEdges && !hasOutgoingEdges) {
      // Node is completely isolated - dangling
      errors.push({
        id: `dangling-${activity.id}`,
        severity: 'error',
        rule: 'no-dangling-nodes',
        message: `Step "${activity.name || activity.id}" is not connected to the workflow`,
        nodeId: activity.id,
        suggestion: "Connect this step to other steps in the workflow, or remove it if it's not needed",
      })
    }
  }

  return errors
}

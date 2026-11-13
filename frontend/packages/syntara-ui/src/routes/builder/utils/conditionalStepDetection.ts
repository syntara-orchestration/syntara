/**
 * Utilities for detecting if a workflow step may not always execute
 * due to being inside a conditional, switch, or loop construct.
 */

type Activity = {
  id: string
  type: string
}

type Edge = {
  source: string
  target: string
}

const CONDITIONAL_NODE_TYPES = new Set(['condition', 'switch', 'loop', 'loop_each'])

/**
 * Extract step ID from a template expression like "${step.field}" or "${step}".
 * Returns null if the expression doesn't reference a step.
 */
export function extractStepIdFromExpression(expression: string): string | null {
  const match = expression.match(/^\$\{([^.}]+)/)
  return match ? match[1] : null
}

/**
 * Determine if a step may not always execute because it's inside a conditional construct.
 *
 * A step is conditional if there exists a path from the trigger to the step that goes
 * through a conditional node (condition, switch, loop).
 *
 * @param stepId - The ID of the step to check
 * @param activities - All activities in the workflow
 * @param edges - All edges in the workflow
 * @param triggerIds - IDs of trigger nodes (starting points)
 * @returns true if the step may not execute, false if it always executes
 */
export function isStepConditional(
  stepId: string,
  activities: Activity[],
  edges: Edge[],
  triggerIds: string[]
): boolean {
  // Build adjacency list for graph traversal
  const graph = new Map<string, Set<string>>()
  for (const edge of edges) {
    if (!graph.has(edge.source)) {
      graph.set(edge.source, new Set())
    }
    graph.get(edge.source)!.add(edge.target)
  }

  // Build activity type lookup
  const activityTypes = new Map(activities.map((a) => [a.id, a.type]))

  // BFS from triggers to find all paths to the step
  const visited = new Set<string>()
  const queue: string[] = [...triggerIds]
  let foundConditionalInPath = false

  while (queue.length > 0) {
    const current = queue.shift()!

    if (visited.has(current)) continue
    visited.add(current)

    // Check if this is a conditional node
    const currentType = activityTypes.get(current)
    if (currentType && CONDITIONAL_NODE_TYPES.has(currentType)) {
      foundConditionalInPath = true
    }

    // If we reached the target step
    if (current === stepId) {
      // If we found a conditional node in any path to this step, it's conditional
      if (foundConditionalInPath) {
        return true
      }
    }

    // Add neighbors to queue
    const neighbors = graph.get(current) ?? new Set()
    for (const neighbor of neighbors) {
      if (!visited.has(neighbor)) {
        queue.push(neighbor)
      }
    }
  }

  return false
}

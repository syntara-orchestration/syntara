import type { ActivityState } from '../../../workflows/execution/types'
import type { EdgeConnection } from '../../types/edge'

import { ACTIVITY_STATUS, isBranchHandle, isTerminalState } from './executionHelpers'

/**
 * Utility class for traversing workflow graphs to determine execution state.
 *
 * This module provides functions for:
 * - Detecting if a node should be marked as "skipped"
 * - Finding pending nodes downstream from a given node
 * - Traversing the workflow graph with memoization to avoid redundant work
 */
export class WorkflowTraversal {
  /**
   * Check if there are any pending or running nodes downstream from the given activity.
   *
   * This is used to determine if a node should remain in "pending" state rather than
   * being marked as "skipped". If downstream nodes are pending/running, the execution
   * could still reach this node.
   *
   * @param startNodeId - The activity ID to start traversing from
   * @param activityStates - Map of activity IDs to their execution states
   * @param edges - All edges in the workflow
   * @param visited - Set of visited node IDs to prevent infinite loops
   * @returns true if any downstream node is pending or running
   *
   * @example
   * // Check if a node could still be reached by execution
   * if (WorkflowTraversal.hasDownstreamPendingNodes(nodeId, states, edges)) {
   *   // Keep node as pending - execution might reach it
   * } else {
   *   // Node can be marked as skipped - execution won't reach it
   * }
   */
  static hasDownstreamPendingNodes(
    startNodeId: string,
    activityStates: Map<string, ActivityState>,
    edges: EdgeConnection[],
    visited: Set<string> = new Set()
  ): boolean {
    // Prevent infinite recursion from cycles in the graph
    if (visited.has(startNodeId)) {
      return false
    }
    visited.add(startNodeId)

    // Find all outgoing edges from this node
    const outgoingEdges = edges.filter((edge) => edge.source === startNodeId)

    for (const edge of outgoingEdges) {
      const targetState = activityStates.get(edge.target)

      // If target is pending or running, we found a downstream pending node
      if (
        targetState &&
        (targetState.status === ACTIVITY_STATUS.PENDING || targetState.status === ACTIVITY_STATUS.RUNNING)
      ) {
        return true
      }

      // Recursively check downstream nodes from the target
      // Create a new visited set to pass down the recursion chain
      if (this.hasDownstreamPendingNodes(edge.target, activityStates, edges, new Set(visited))) {
        return true
      }
    }

    return false
  }

  /**
   * Determine if a node should be marked as "skipped" based on execution flow.
   *
   * A node is skipped when:
   * 1. It's on a non-taken branch (branching node completed without taking this path)
   * 2. All incoming nodes are either skipped OR completed/failed/cancelled, and the node never started
   * 3. No downstream nodes are still pending or running (execution won't reach it)
   *
   * This implements cascading skip logic: if a parent is skipped, children are skipped too.
   *
   * When `skipInferenceActivityIds` is provided (copy-to-editor), only IDs in that set
   * may be inferred as skipped. Nodes added after the copy keep no execution status.
   *
   * @returns true if the node should be marked as skipped
   *
   * @example
   * // Check if a node on a conditional branch should be skipped
   * const shouldSkip = WorkflowTraversal.shouldMarkAsSkipped({ activityId: nodeId, activityStates: states, edges })
   * if (shouldSkip) {
   *   activity.__executionState = { status: 'skipped' }
   * }
   */
  static shouldMarkAsSkipped(params: {
    activityId: string
    activityStates: Map<string, ActivityState>
    edges: EdgeConnection[]
    visited?: Set<string>
    skipInferenceActivityIds?: ReadonlySet<string>
  }): boolean {
    const { activityId, activityStates, edges, visited = new Set(), skipInferenceActivityIds } = params
    // Nodes outside the copied-run allowlist must not inherit inferred Skipped status
    if (skipInferenceActivityIds && !skipInferenceActivityIds.has(activityId)) {
      return false
    }

    // Prevent infinite recursion from cycles
    if (visited.has(activityId)) {
      return false
    }
    visited.add(activityId)

    // Step 1: If node has execution state (started), it's not skipped
    const activityState = activityStates.get(activityId)
    if (activityState) {
      return false
    }

    // Step 2: If any downstream node is pending/running, keep this node as pending
    // (execution could still reach it)
    if (this.hasDownstreamPendingNodes(activityId, activityStates, edges)) {
      return false
    }

    // Step 3: Find all incoming edges to this activity
    const incomingEdges = edges.filter((edge) => edge.target === activityId)

    if (incomingEdges.length === 0) {
      return false // No incoming edges (trigger nodes or orphans) - not skipped
    }

    // Step 4: Check if node is on a non-taken branch
    const isOnNonTakenBranch = this.isOnNonTakenBranch(incomingEdges, activityStates)
    if (isOnNonTakenBranch) {
      return true // Node is on a conditional/approval branch that wasn't taken
    }

    // Step 5: Check if all incoming nodes are either skipped or in terminal states
    // This handles cascading skips (parent skipped → children skipped)
    return this.areAllIncomingNodesSkippedOrTerminal({
      incomingEdges,
      activityStates,
      edges,
      visited,
      skipInferenceActivityIds,
    })
  }

  /**
   * Check if a node is on a non-taken branch from a conditional or approval node.
   *
   * A branch is "non-taken" if:
   * - The incoming edge uses a branch handle (true/false/approved/rejected)
   * - The source node completed (took one path but not this one)
   *
   * @private
   */
  private static isOnNonTakenBranch(
    incomingEdges: EdgeConnection[],
    activityStates: Map<string, ActivityState>
  ): boolean {
    // Filter for branch edges (from conditional or approval nodes)
    const branchEdges = incomingEdges.filter((edge) => isBranchHandle(edge.sourceHandle))

    if (branchEdges.length === 0) {
      return false // No branch edges
    }

    // Check if all branching source nodes completed
    // If they completed and this node never started, they took a different branch
    const allBranchSourcesCompleted = branchEdges.every((edge) => {
      const sourceState = activityStates.get(edge.source)
      return sourceState && isTerminalState(sourceState.status)
    })

    return allBranchSourcesCompleted
  }

  /**
   * Check if all incoming nodes are either skipped or in terminal states.
   *
   * This implements cascading skip logic. If all paths into a node are either:
   * - Skipped (parent was skipped)
   * - Terminal (completed/failed/cancelled)
   *
   * Then this node was never reached by execution and should be skipped.
   *
   * @private
   */
  private static areAllIncomingNodesSkippedOrTerminal(params: {
    incomingEdges: EdgeConnection[]
    activityStates: Map<string, ActivityState>
    edges: EdgeConnection[]
    visited: Set<string>
    skipInferenceActivityIds?: ReadonlySet<string>
  }): boolean {
    const { incomingEdges, activityStates, edges, visited, skipInferenceActivityIds } = params
    return incomingEdges.every((edge) => {
      const sourceState = activityStates.get(edge.source)

      // If source is in a terminal state, it's done
      if (sourceState && isTerminalState(sourceState.status)) {
        return true
      }

      // If source should be skipped, this counts too (cascading skip)
      return this.shouldMarkAsSkipped({
        activityId: edge.source,
        activityStates,
        edges,
        visited: new Set(visited),
        skipInferenceActivityIds,
      })
    })
  }
}

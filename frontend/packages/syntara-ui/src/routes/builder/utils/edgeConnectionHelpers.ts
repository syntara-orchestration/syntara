import { EdgeHandleEnum } from '@syntara/contracts'
import type { ReactFlowInstance, Node } from '@xyflow/react'

import { FlowNodeType } from '../../../constants'
import { generateUUID } from '../../../utils/generateUUID'
import type { FlowPosition } from '../types'

import { EdgeFactory } from './EdgeFactory'
import { isSwitchCasePort, SWITCH_CASE_PORT_PREFIX } from './switchCaseHelpers'
import type { EdgeType } from './workflowToGraph'

/**
 * Check if a condition node has placeholder nodes for true/false branches
 */
function hasConditionNodePlaceholders(nodes: Node[], sourceId: string): boolean {
  return nodes.some((n) => n.id === `placeholder-${sourceId}-true` || n.id === `placeholder-${sourceId}-false`)
}

/**
 * Check if a loop node has placeholder nodes for done/loop branches
 */
function hasLoopNodePlaceholders(nodes: Node[], sourceId: string): boolean {
  return nodes.some((n) => n.id === `placeholder-${sourceId}-done` || n.id === `placeholder-${sourceId}-loop`)
}

/**
 * Check if a switch node has placeholder nodes for case/default branches
 */
function hasSwitchNodePlaceholders(nodes: Node[], sourceId: string): boolean {
  return nodes.some(
    (n) =>
      n.id.startsWith(`placeholder-${sourceId}-${SWITCH_CASE_PORT_PREFIX}`) ||
      n.id === `placeholder-${sourceId}-default`
  )
}

/**
 * Parameters for creating edges when connecting nodes from the add panel
 */
export type EdgeConnectionParams = {
  sourceId: string
  targetId: string
  edgeIdToReplace?: string | null
  targetNodeId?: string | null
  sourceHandle?: string
  targetHandle?: string
  onAddNode: (
    sourceId: string,
    targetId?: string,
    edgeId?: string,
    handle?: string,
    desiredPosition?: FlowPosition
  ) => void
}

/**
 * Result of edge connection operation
 */
export type EdgeConnectionResult = {
  /** New edges to add to the graph */
  edgesToAdd: EdgeType[]
  /** Edge IDs to remove from the graph */
  edgeIdsToRemove: string[]
  /** Placeholder node ID to remove */
  placeholderIdToRemove: string | null
  /** Whether to remove button edge class from source node */
  shouldRemoveButtonEdgeClass: boolean
  /** Activity reordering operation (targetId should move before this node) */
  activityReorderTarget: string | null
}

/**
 * Removes button edge styling class from a node
 */
function removeButtonEdgeClass(nodes: Node[], sourceId: string): Node[] {
  return nodes.map((n) => {
    if (n.id === sourceId) {
      const className = (n.className ?? '').replace('has-button-edge', '').trim()
      return { ...n, className }
    }
    return n
  })
}

/**
 * Calculate edge connections when adding a node from the add panel.
 *
 * This handles three scenarios:
 * 1. Adding a node between two existing nodes (edge replacement)
 * 2. Adding a node to a loop node (creates loop-back edge)
 * 3. Adding a node to a regular node (simple edge creation)
 *
 * @param params - Connection parameters
 * @param reactFlowInstance - React Flow instance for node lookup
 * @returns Connection result with edges to add/remove and node updates
 */
export function calculateEdgeConnection(
  params: EdgeConnectionParams,
  reactFlowInstance: ReactFlowInstance
): EdgeConnectionResult {
  const { sourceId, targetId, edgeIdToReplace, targetNodeId, sourceHandle, targetHandle, onAddNode } = params

  const edgesToAdd: EdgeType[] = []
  const edgeIdsToRemove: string[] = []
  let placeholderIdToRemove: string | null = null
  let shouldRemoveButtonEdgeClass = false
  let activityReorderTarget: string | null = null

  // Create primary edge from source to new target
  const newEdge = EdgeFactory.createEdge({
    source: sourceId,
    target: targetId,
    sourceHandle,
    targetHandle: EdgeHandleEnum.TARGET,
    onAddNode,
  })
  edgesToAdd.push(newEdge)

  // Note: Button edges are automatically filtered by EdgeFactory.removeButtonEdge in the caller
  // We just need to track the old edge to remove if this is a replacement operation
  if (edgeIdToReplace) {
    edgeIdsToRemove.push(edgeIdToReplace)
  }

  // Scenario 1: Edge replacement - insert node between two existing nodes
  if (edgeIdToReplace && targetNodeId) {
    const secondEdge = EdgeFactory.createEdge({
      source: targetId,
      target: targetNodeId,
      sourceHandle: EdgeHandleEnum.SOURCE,
      targetHandle: targetHandle ?? EdgeHandleEnum.TARGET,
      onAddNode,
    })
    edgesToAdd.push(secondEdge)
    activityReorderTarget = targetNodeId
  }

  // Scenario 2: Loop handle - create loop-back edge
  if (sourceHandle === EdgeHandleEnum.LOOP && !edgeIdToReplace) {
    const loopBackEdge = EdgeFactory.createEdge({
      source: targetId,
      target: sourceId,
      sourceHandle: EdgeHandleEnum.SOURCE,
      targetHandle: EdgeHandleEnum.END,
      onAddNode,
    })
    edgesToAdd.push(loopBackEdge)
  }

  // Determine placeholder node to remove
  const isConditionHandle = sourceHandle === EdgeHandleEnum.TRUE || sourceHandle === EdgeHandleEnum.FALSE
  const isLoopHandle = sourceHandle === EdgeHandleEnum.DONE || sourceHandle === EdgeHandleEnum.LOOP
  const isSwitchLikeHandle = isSwitchCasePort(sourceHandle) || sourceHandle === EdgeHandleEnum.DEFAULT
  placeholderIdToRemove =
    isConditionHandle || isLoopHandle || isSwitchLikeHandle
      ? `placeholder-${sourceId}-${sourceHandle}`
      : `placeholder-${sourceId}`

  // Check if button edge class should be removed from source node
  const nodes = reactFlowInstance.getNodes()
  const sourceNode = nodes.find((n) => n.id === sourceId)

  if (sourceNode) {
    const filteredNodes = nodes.filter((n) => n.id !== placeholderIdToRemove)

    // Keep button edge class only if source node still has other placeholders
    const hasOtherPlaceholders =
      (sourceNode.type === FlowNodeType.CONDITION && hasConditionNodePlaceholders(filteredNodes, sourceId)) ||
      (sourceNode.type === FlowNodeType.LOOP && hasLoopNodePlaceholders(filteredNodes, sourceId)) ||
      (sourceNode.type === FlowNodeType.SWITCH && hasSwitchNodePlaceholders(filteredNodes, sourceId))

    shouldRemoveButtonEdgeClass = !hasOtherPlaceholders
  }

  return {
    edgesToAdd,
    edgeIdsToRemove,
    placeholderIdToRemove,
    shouldRemoveButtonEdgeClass,
    activityReorderTarget,
  }
}

// SECURITY: Global concurrency tracking to prevent DoS via excessive concurrent polling
// Use Set for atomic add/delete operations instead of counter to prevent race conditions
const activeConnections = new Set<string>()
const MAX_CONCURRENT_CONNECTIONS = 5
// SECURITY: Track active timers for cleanup and limit total timer count
const activeTimers = new Set<NodeJS.Timeout>()
// SECURITY: Prevent timer resource exhaustion - each connection can retry up to 40 times,
// so max timers = MAX_CONCURRENT_CONNECTIONS * 40 = 200
const MAX_TOTAL_TIMERS = 200

/**
 * Reset the active polling connections state.
 * FOR TESTING ONLY - allows tests to reset state between test cases.
 * @internal
 */
export function resetPollingConnectionCounter(): void {
  activeConnections.clear()
  // Clear any remaining timers
  activeTimers.forEach((timer) => clearTimeout(timer))
  activeTimers.clear()
}

/**
 * Apply edge connection result to React Flow instance with retry logic for node measurement.
 *
 * Waits for target node to be measured before creating edges.
 *
 * SECURITY: Limited to 5 concurrent connections to prevent client-side resource exhaustion.
 *
 * @param result - Connection result from calculateEdgeConnection
 * @param params - Original connection parameters
 * @param targetId - ID of the target node
 * @param reactFlowInstance - React Flow instance
 * @param onComplete - Callback when connection is complete
 */
export function applyEdgeConnection(
  result: EdgeConnectionResult,
  params: EdgeConnectionParams,
  targetId: string,
  reactFlowInstance: ReactFlowInstance,
  onComplete?: () => void
): void {
  // SECURITY: Prevent DoS - reject if too many concurrent connections
  if (activeConnections.size >= MAX_CONCURRENT_CONNECTIONS) {
    // eslint-disable-next-line no-console
    console.warn(
      `Edge connection rejected: max concurrent limit (${MAX_CONCURRENT_CONNECTIONS}) reached. ` +
        `This may indicate a malicious workflow or performance issue.`
    )
    onComplete?.()
    return
  }

  // SECURITY: Ensure cleanup on all exit paths (success, timer-limit, timeout)
  const connectionId = `${params.sourceId}-${targetId}-${generateUUID()}`
  activeConnections.add(connectionId)

  let attempts = 0
  const checkAndConnect = () => {
    const nodes = reactFlowInstance.getNodes()
    const targetNode = nodes.find((n) => n.id === targetId)

    if (targetNode?.measured) {
      // Add new edges, removing button edges and old edges
      reactFlowInstance.setEdges((eds) => {
        // Remove button edge for the source handle
        let filtered = EdgeFactory.removeButtonEdge(params.sourceId, eds as EdgeType[], params.sourceHandle)
        // Remove old edge if replacement
        filtered = filtered.filter((e) => !result.edgeIdsToRemove.includes(e.id))
        // Add new edges
        return [...filtered, ...result.edgesToAdd] as EdgeType[]
      })

      // Remove placeholder node and update button edge class
      if (result.placeholderIdToRemove) {
        reactFlowInstance.setNodes((nds) => {
          // Only update if placeholder actually exists
          const hasPlaceholder = nds.some((n) => n.id === result.placeholderIdToRemove)
          if (!hasPlaceholder) return nds

          const filtered = nds.filter((n) => n.id !== result.placeholderIdToRemove)
          const sourceNode = filtered.find((n) => n.id === params.sourceId)
          if (!sourceNode) return filtered

          // Check if we should keep or remove the button edge class
          if (sourceNode.type === FlowNodeType.CONDITION && hasConditionNodePlaceholders(filtered, params.sourceId)) {
            return filtered
          }
          if (sourceNode.type === FlowNodeType.LOOP && hasLoopNodePlaceholders(filtered, params.sourceId)) {
            return filtered
          }
          if (sourceNode.type === FlowNodeType.SWITCH && hasSwitchNodePlaceholders(filtered, params.sourceId)) {
            return filtered
          }

          return removeButtonEdgeClass(filtered, params.sourceId)
        })
      }

      // Remove this connection from active set
      activeConnections.delete(connectionId)
      onComplete?.()
    } else if (attempts++ < 40) {
      // SECURITY: Check if we've exceeded the total timer limit before creating a new timer
      if (activeTimers.size >= MAX_TOTAL_TIMERS) {
        // eslint-disable-next-line no-console
        console.warn(
          `Timer limit reached (${MAX_TOTAL_TIMERS}). Stopping retries for edge connection to prevent resource exhaustion.`
        )
        activeConnections.delete(connectionId)
        onComplete?.()
        return
      }

      const timerId = setTimeout(() => {
        activeTimers.delete(timerId)
        checkAndConnect()
      }, 50)
      activeTimers.add(timerId)
    } else {
      // Timeout - cleanup connection
      activeConnections.delete(connectionId)
      onComplete?.()
    }
  }

  checkAndConnect()
}

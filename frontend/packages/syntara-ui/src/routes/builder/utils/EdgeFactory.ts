import { EdgeHandleEnum } from '@syntara/contracts'
import { addEdge } from '@xyflow/react'

import type { EdgeConnection } from '../types/edge'

import { getButtonEdgeId, isBranchHandle } from './edgeHelpers'
import { markerEnd, type EdgeType } from './workflowToGraph'

export type CreateEdgeOptions = {
  source: string
  target: string
  sourceHandle?: string
  targetHandle?: string
  onAddNode?: (sourceId: string, targetId?: string, edgeId?: string, handle?: string) => void
}

/**
 * Centralized edge creation utility.
 *
 * This factory ensures consistent edge creation across:
 * - Manual connections (BuilderFlow.tsx)
 * - ButtonEdge automatic connections (BuilderContent.tsx)
 * - Edge insertions and replacements
 *
 * All edges created through this factory have:
 * - Consistent ID format
 * - Proper typing (EdgeType)
 * - Standard markerEnd styling
 * - Optional onAddNode callback in data
 */
export class EdgeFactory {
  /**
   * Creates a new edge with standard configuration.
   *
   * @param options - Edge creation options
   * @returns Properly typed and configured edge
   *
   * @example
   * ```typescript
   * const edge = EdgeFactory.createEdge({
   *   source: 'task-1',
   *   target: 'task-2',
   *   sourceHandle: 'source',
   *   targetHandle: 'target',
   *   onAddNode: handleAddNodeFromEdge
   * })
   * ```
   */
  static createEdge(options: CreateEdgeOptions): EdgeType {
    const { source, target, sourceHandle, targetHandle, onAddNode } = options

    // Generate edge ID based on sourceHandle
    // Include sourceHandle in ID for conditional and approval node branch edges
    const edgeId = isBranchHandle(sourceHandle) ? `${source}-${sourceHandle}-${target}` : `${source}-${target}`

    // Determine edge type based on handles:
    // - loopBack: edges connecting TO loop's end handle (looping back)
    // - loopOutgoing: edges FROM loop's loop handle (exiting the loop to the next iteration)
    // - loopDone: edges FROM loop's done handle (exiting the loop when complete)
    // - default: all other edges
    let edgeType: string = 'default'
    if (targetHandle === EdgeHandleEnum.END) {
      edgeType = 'loopBack'
    } else if (sourceHandle === EdgeHandleEnum.LOOP) {
      edgeType = 'loopOutgoing'
    } else if (sourceHandle === EdgeHandleEnum.DONE) {
      edgeType = 'loopDone'
    }

    return {
      id: edgeId,
      source,
      target,
      ...(sourceHandle ? { sourceHandle } : {}),
      targetHandle: targetHandle ?? EdgeHandleEnum.TARGET,
      type: edgeType,
      markerEnd,
      ...(onAddNode ? { data: { onAddNode } } : {}),
    }
  }

  /**
   * Adds an edge to an existing edge array using React Flow's addEdge helper.
   *
   * This ensures proper edge deduplication and validation.
   *
   * @param edge - Edge to add
   * @param edges - Existing edges array
   * @returns Updated edges array
   *
   * @example
   * ```typescript
   * setEdges((eds) => EdgeFactory.addEdge(newEdge, eds))
   * ```
   */
  static addEdge(edge: EdgeType, edges: EdgeType[]): EdgeType[] {
    return addEdge(edge, edges as never)
  }

  /**
   * Creates and adds an edge in one operation.
   *
   * @param options - Edge creation options
   * @param edges - Existing edges array
   * @returns Updated edges array with new edge
   *
   * @example
   * ```typescript
   * setEdges((eds) => EdgeFactory.createAndAdd({
   *   source: 'task-1',
   *   target: 'task-2',
   *   onAddNode: handleAddNodeFromEdge
   * }, eds))
   * ```
   */
  static createAndAdd(options: CreateEdgeOptions, edges: EdgeType[]): EdgeType[] {
    const edge = this.createEdge(options)
    return this.addEdge(edge, edges)
  }

  /**
   * Replaces an edge by removing the old one and adding a new one.
   *
   * @param oldEdgeId - ID of edge to replace
   * @param options - New edge creation options
   * @param edges - Existing edges array
   * @returns Updated edges array
   *
   * @example
   * ```typescript
   * setEdges((eds) => EdgeFactory.replaceEdge('old-edge-id', {
   *   source: 'task-1',
   *   target: 'task-2'
   * }, eds))
   * ```
   */
  static replaceEdge(oldEdgeId: string, options: CreateEdgeOptions, edges: EdgeType[]): EdgeType[] {
    const filtered = edges.filter((e) => e.id !== oldEdgeId)
    return this.createAndAdd(options, filtered)
  }

  /**
   * Removes button edges for a specific node.
   *
   * Button edges have IDs in the format:
   * - Regular nodes: `button-${nodeId}`
   * - Condition nodes: `button-${nodeId}-true` or `button-${nodeId}-false`
   * - Loop nodes: `button-${nodeId}-done` or `button-${nodeId}-loop`
   *
   * @param nodeId - Node ID to remove button edges for
   * @param edges - Existing edges array
   * @param sourceHandle - Optional specific handle to remove (for condition/loop nodes)
   * @returns Filtered edges array
   *
   * @example
   * ```typescript
   * // Remove all button edges for a node
   * setEdges((eds) => EdgeFactory.removeButtonEdge('task-1', eds))
   *
   * // Remove button edge for specific handle (condition node)
   * setEdges((eds) => EdgeFactory.removeButtonEdge('condition-1', eds, 'true'))
   *
   * // Remove button edge for specific handle (loop node)
   * setEdges((eds) => EdgeFactory.removeButtonEdge('loop-1', eds, 'done'))
   * setEdges((eds) => EdgeFactory.removeButtonEdge('loop-1', eds, 'loop'))
   * ```
   */
  static removeButtonEdge(nodeId: string, edges: EdgeType[], sourceHandle?: string): EdgeType[] {
    const branchHandles = [
      EdgeHandleEnum.TRUE,
      EdgeHandleEnum.FALSE,
      EdgeHandleEnum.DONE,
      EdgeHandleEnum.LOOP,
      EdgeHandleEnum.APPROVED,
      EdgeHandleEnum.REJECTED,
    ] as const

    if (sourceHandle && (branchHandles as readonly string[]).includes(sourceHandle)) {
      // Remove specific handle button edge for condition/approval/loop nodes
      const buttonEdgeId = getButtonEdgeId(nodeId, sourceHandle)
      return edges.filter((e) => e.id !== buttonEdgeId)
    }
    // Remove regular button edge and any condition/approval/loop handle button edges
    return edges.filter(
      (e) =>
        e.id !== getButtonEdgeId(nodeId) &&
        e.id !== getButtonEdgeId(nodeId, EdgeHandleEnum.TRUE) &&
        e.id !== getButtonEdgeId(nodeId, EdgeHandleEnum.FALSE) &&
        e.id !== getButtonEdgeId(nodeId, EdgeHandleEnum.APPROVED) &&
        e.id !== getButtonEdgeId(nodeId, EdgeHandleEnum.REJECTED) &&
        e.id !== getButtonEdgeId(nodeId, EdgeHandleEnum.DONE) &&
        e.id !== getButtonEdgeId(nodeId, EdgeHandleEnum.LOOP)
    )
  }

  /**
   * Converts EdgeType to EdgeConnection (for workflow store).
   *
   * @param edge - React Flow edge
   * @returns Simplified edge connection
   */
  static toEdgeConnection(edge: EdgeType): EdgeConnection {
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle,
      targetHandle: edge.targetHandle,
    }
  }

  /**
   * Converts multiple EdgeTypes to EdgeConnections.
   *
   * @param edges - React Flow edges
   * @returns Array of edge connections
   */
  static toEdgeConnections(edges: EdgeType[]): EdgeConnection[] {
    return edges.map((e) => this.toEdgeConnection(e))
  }
}

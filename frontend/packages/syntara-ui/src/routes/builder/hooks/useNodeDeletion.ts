import { EdgeHandleEnum } from '@syntara/contracts'
import type { OnNodesDelete } from '@xyflow/react'
import { useCallback, type Dispatch, type MutableRefObject, type SetStateAction } from 'react'

import { FlowNodeType } from '../../../constants'
import { useWorkflowStore, useWorkflowStoreActions } from '../../../stores/useWorkflowStore'
import { parseTriggerIndex } from '../../../utils/triggerNodeIds'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { EdgeConnection } from '../types/edge'
import { EdgeFactory } from '../utils/EdgeFactory'
import { buildTriggerIndexRemappping, remapTriggerIdsInEdges } from '../utils/triggerIndexRemapping'
import type { EdgeType } from '../utils/workflowToGraph'

export type LoopReconnection = {
  source: string
  target: string
  targetHandle: string
  sourceHandle?: string
}

/**
 * Collect real trigger IDs for deleted trigger nodes.
 *
 * When workflows are loaded from the backend, edges may use real trigger IDs
 * (e.g., "activity_fb2060fd_...") instead of display IDs (e.g., "trigger-0").
 * This function gets the real IDs so edges can be filtered correctly.
 */
function collectDeletedTriggerRealIds(triggerIndices: number[]): Set<string> {
  const deletedTriggerRealIds = new Set<string>()
  const triggers = useWorkflowStore.getState().currentWorkflow?.triggers

  triggerIndices.forEach((triggerIndex) => {
    const trigger = triggers?.[triggerIndex]
    const realId = (trigger as { id?: string } | undefined)?.id
    if (realId) {
      deletedTriggerRealIds.add(realId)
    }
  })

  return deletedTriggerRealIds
}

/**
 * Categorize deleted nodes into activities and triggers.
 */
function categorizeDeletedNodes(
  deletedNodeIds: Set<string>,
  nodes: NodeType[]
): { activityIds: string[]; triggerIndices: number[] } {
  const activityIds: string[] = []
  const triggerIndices: number[] = []

  Array.from(deletedNodeIds).forEach((nodeId) => {
    const node = nodes.find((n) => n.id === nodeId)
    if (!node) return

    if (node.type === FlowNodeType.TRIGGER) {
      const triggerIndex = parseTriggerIndex(node.id)
      if (triggerIndex !== undefined) {
        triggerIndices.push(triggerIndex)
      }
    } else if ((node.type as string) !== FlowNodeType.PLACEHOLDER) {
      activityIds.push(node.id)
    }
  })

  return { activityIds, triggerIndices }
}

function tryReconnectLoopForDeletedNode(
  deletedNodeId: string,
  storedEdges: EdgeConnection[],
  deletedNodeIds: Set<string>,
  nodes: NodeType[]
): LoopReconnection | undefined {
  const loopBackEdge = storedEdges.find(
    (edge) => edge.source === deletedNodeId && edge.targetHandle === EdgeHandleEnum.END
  )

  if (!loopBackEdge || deletedNodeIds.has(loopBackEdge.target)) {
    return undefined
  }

  const pickIncomingEdge = (targetId: string) => {
    const candidates = storedEdges.filter((edge) => edge.target === targetId)
    return (
      candidates.find(
        (edge) =>
          !deletedNodeIds.has(edge.source) &&
          !(edge.source === loopBackEdge.target && edge.sourceHandle === EdgeHandleEnum.LOOP)
      ) ?? candidates.find((edge) => deletedNodeIds.has(edge.source))
    )
  }

  let cursorTarget = deletedNodeId
  const visited = new Set<string>()
  let incomingEdge = pickIncomingEdge(cursorTarget)

  while (incomingEdge && deletedNodeIds.has(incomingEdge.source) && !visited.has(cursorTarget)) {
    visited.add(cursorTarget)
    cursorTarget = incomingEdge.source
    incomingEdge = pickIncomingEdge(cursorTarget)
  }

  if (!incomingEdge || deletedNodeIds.has(incomingEdge.source)) {
    return undefined
  }

  const isFromLoopNode =
    incomingEdge.source === loopBackEdge.target && incomingEdge.sourceHandle === EdgeHandleEnum.LOOP

  if (isFromLoopNode) {
    return undefined
  }

  const newLastNode = nodes.find((n) => n.id === incomingEdge.source)
  const sourceHandle = newLastNode?.type === FlowNodeType.LOOP ? EdgeHandleEnum.DONE : EdgeHandleEnum.SOURCE

  return {
    source: incomingEdge.source,
    target: loopBackEdge.target,
    targetHandle: EdgeHandleEnum.END,
    sourceHandle,
  }
}

export function findLoopReconnections(
  storedEdges: EdgeConnection[],
  deletedNodeIds: Set<string>,
  nodes: NodeType[]
): LoopReconnection[] {
  const loopReconnections: LoopReconnection[] = []

  deletedNodeIds.forEach((deletedNodeId) => {
    const reconnection = tryReconnectLoopForDeletedNode(deletedNodeId, storedEdges, deletedNodeIds, nodes)
    if (reconnection) {
      loopReconnections.push(reconnection)
    }
  })

  return loopReconnections
}

type UseNodeDeletionParams = {
  nodes: NodeType[]
  edges: EdgeConnection[]
  setNodes: Dispatch<SetStateAction<NodeType[]>>
  setEdges: Dispatch<SetStateAction<EdgeType[]>>
  isDeletingRef: MutableRefObject<boolean>
  onAddNodeFromEdge?: (sourceNodeId: string, nodeType?: string, activityId?: string, sourceHandle?: string) => void
  onNodesDeleted?: (nodeIds: string[]) => void
  onError?: (message: string) => void
}

export function useNodeDeletion({
  nodes,
  edges: storedEdges,
  setNodes,
  setEdges,
  isDeletingRef,
  onAddNodeFromEdge,
  onNodesDeleted,
  onError,
}: UseNodeDeletionParams) {
  const { batchRemoveNodesAndEdges } = useWorkflowStoreActions()

  const onNodesDelete: OnNodesDelete = useCallback(
    (deletedNodes) => {
      isDeletingRef.current = true
      const deletedNodeIds = new Set(deletedNodes.map((n) => n.id))

      // SECURITY: Perform ALL graph traversal and data computation BEFORE any state mutations.
      // If traversal throws an error, no state changes will have been applied (transaction-like behavior).
      try {
        // CRITICAL: When deleting a loop node, also delete all nodes in its loop body
        // Loop body nodes are identified by following edges from the loop node's 'loop' handle
        // until we encounter a loop-back edge (targetHandle === 'end')
        deletedNodes.forEach((node) => {
          if (node.type === FlowNodeType.LOOP) {
            const loopNodeId = node.id

            // SECURITY: Collect loop body nodes in a separate set to avoid mutating deletedNodeIds
            // during traversal. Only merge into deletedNodeIds after successful completion.
            const loopBodyNodes = new Set<string>()
            const visited = new Set<string>()

            // BFS to collect all nodes in the loop body
            const queue: string[] = []

            // Find the initial loop body nodes (direct targets of the 'loop' handle)
            const loopEdges = storedEdges.filter(
              (edge) => edge.source === loopNodeId && edge.sourceHandle === EdgeHandleEnum.LOOP
            )

            loopEdges.forEach((edge) => {
              if (!deletedNodeIds.has(edge.target)) {
                queue.push(edge.target)
              }
            })

            // SECURITY: Pre-build edge lookup map for O(1) access instead of O(n) filter
            const edgesBySource = new Map<string, EdgeConnection[]>()
            storedEdges.forEach((edge) => {
              const edges = edgesBySource.get(edge.source) ?? []
              edges.push(edge)
              edgesBySource.set(edge.source, edges)
            })

            // SECURITY: Get total node count to detect malicious deeply connected graphs
            // This provides defense-in-depth: we compare loop body size to total node count
            // to catch cycles early (see check on line 214)
            const totalNodeCount = nodes.length

            // SECURITY: The primary cycle defense is loopBodyNodes.size > totalNodeCount (line 214).
            // That check catches real cycles reliably because a loop body can never legitimately
            // contain more nodes than the entire workflow.
            //
            // This iteration limit is a secondary safety net only — set high enough (10,000)
            // that no legitimate workflow hits it, while still bounding worst-case CPU time.
            const MAX_ITERATIONS = 10_000
            let iterations = 0

            while (queue.length > 0 && iterations < MAX_ITERATIONS) {
              iterations++
              const currentNodeId = queue[0]
              queue.shift()
              // Check against both deletedNodeIds (originally deleted) and loopBodyNodes (found during traversal)
              if (visited.has(currentNodeId) || deletedNodeIds.has(currentNodeId) || loopBodyNodes.has(currentNodeId))
                continue

              visited.add(currentNodeId)
              loopBodyNodes.add(currentNodeId)

              // SECURITY: Break immediately if loop body exceeds total node count (cycle detected)
              if (loopBodyNodes.size > totalNodeCount) {
                throw new Error(
                  `Loop body size (${loopBodyNodes.size}) exceeds total node count (${totalNodeCount}). ` +
                    `The workflow graph contains unexpected cycles. Please check your workflow structure.`
                )
              }

              // SECURITY: Use Map lookup (O(1)) instead of filter (O(n))
              const outgoingEdges = (edgesBySource.get(currentNodeId) ?? []).filter(
                (edge) => !(edge.target === loopNodeId && edge.targetHandle === EdgeHandleEnum.END)
              )

              outgoingEdges.forEach((edge) => {
                if (!visited.has(edge.target) && !deletedNodeIds.has(edge.target) && !loopBodyNodes.has(edge.target)) {
                  queue.push(edge.target)
                }
              })
            }

            if (iterations >= MAX_ITERATIONS) {
              throw new Error(
                `Loop body traversal exceeded maximum iterations (${MAX_ITERATIONS}). ` +
                  `The workflow graph may be malformed or contain cycles. Please check your workflow structure.`
              )
            }

            // SECURITY: Only merge loop body nodes into deletedNodeIds after successful traversal
            // This ensures deletedNodeIds remains unmodified if traversal fails
            loopBodyNodes.forEach((nodeId) => deletedNodeIds.add(nodeId))
          }
        })

        // Compute all derived data BEFORE any state mutations (transaction-like approach)
        const placeholderIdsToRemove = new Set(Array.from(deletedNodeIds).map((id) => `placeholder-${id}`))

        // Categorize deleted nodes and collect real trigger IDs
        const { activityIds, triggerIndices } = categorizeDeletedNodes(deletedNodeIds, nodes)
        const deletedTriggerRealIds = collectDeletedTriggerRealIds(triggerIndices)

        const loopReconnections = findLoopReconnections(storedEdges, deletedNodeIds, nodes)

        // Filter edges by both display IDs (trigger-0) and real IDs (activity_fb2060fd_...)
        const filteredEdges = storedEdges.filter(
          (edge) =>
            !deletedNodeIds.has(edge.source) &&
            !deletedNodeIds.has(edge.target) &&
            !deletedTriggerRealIds.has(edge.source) &&
            !deletedTriggerRealIds.has(edge.target)
        )

        // Add loop reconnection edges to the filtered edges
        const edgesWithReconnections = [
          ...filteredEdges,
          ...loopReconnections.map((reconnection) => ({
            id: `${reconnection.source}-${reconnection.target}-end`,
            source: reconnection.source,
            target: reconnection.target,
            sourceHandle: reconnection.sourceHandle,
            targetHandle: reconnection.targetHandle,
          })),
        ]

        // ATOMIC UPDATE: All state mutations happen AFTER traversal completes successfully
        // If traversal threw an error, we never reach here, so state remains unchanged
        batchRemoveNodesAndEdges({
          nodeIds: activityIds,
          edges: edgesWithReconnections,
          triggerIndices,
        })

        // Remove deleted nodes (but don't remap trigger IDs - useBuilderFlowGraph will rebuild them)
        setNodes((currentNodes) =>
          currentNodes.filter((node) => !deletedNodeIds.has(node.id) && !placeholderIdsToRemove.has(node.id))
        )

        // Remove edges connected to deleted nodes and remap trigger display IDs
        setEdges((currentEdges) => {
          const filtered = currentEdges.filter((edge) => {
            // Keep edges if neither source nor target is deleted
            const sourceDeleted = deletedNodeIds.has(edge.source)
            const targetDeleted = deletedNodeIds.has(edge.target) || placeholderIdsToRemove.has(edge.target)
            return !sourceDeleted && !targetDeleted
          })

          // CRITICAL: Remap trigger display IDs in remaining edges using shared utility
          // This ensures consistency with the store's trigger remapping logic
          let remappedEdges = filtered
          if (triggerIndices.length > 0) {
            const triggers = useWorkflowStore.getState().currentWorkflow?.triggers ?? []
            const deletedIndicesSet = new Set(triggerIndices)
            const originalTriggerCount = triggers.length + triggerIndices.length

            const triggerIndexRemap = buildTriggerIndexRemappping(deletedIndicesSet, originalTriggerCount)
            remappedEdges = remapTriggerIdsInEdges(filtered, triggerIndexRemap)
          }

          // Add loop reconnection edges
          const reconnectionEdges = loopReconnections.map((reconnection) =>
            EdgeFactory.createEdge({
              source: reconnection.source,
              target: reconnection.target,
              sourceHandle: reconnection.sourceHandle,
              targetHandle: reconnection.targetHandle,
              onAddNode: onAddNodeFromEdge,
            })
          )

          return [...remappedEdges, ...reconnectionEdges]
        })

        // Clear deletion flag after all updates complete
        setTimeout(() => {
          isDeletingRef.current = false
        }, 100)

        // Notify parent component about deleted nodes
        if (onNodesDeleted) {
          const deletedIds = Array.from(deletedNodeIds)
          onNodesDeleted(deletedIds)
        }
      } catch (error) {
        // SECURITY: Catch iteration limit errors to prevent React component crash
        // No state was mutated because error was thrown before state update calls
        isDeletingRef.current = false
        if (onError) {
          const message =
            error instanceof Error
              ? error.message
              : 'Failed to delete steps. The workflow structure may be too complex.'
          onError(message)
        }
        // Re-throw if no error handler to maintain existing behavior in tests
        if (!onError) throw error
      }
    },
    [
      batchRemoveNodesAndEdges,
      setEdges,
      setNodes,
      nodes,
      storedEdges,
      onAddNodeFromEdge,
      onNodesDeleted,
      onError,
      isDeletingRef,
    ]
  )

  return { onNodesDelete }
}

import type { Dispatch, RefObject, SetStateAction } from 'react'
import { useEffect, useRef, useState } from 'react'

import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'
import { collectAllActivityIds } from '../../../stores/workflowActivityHelpers'
import { buildTriggerNodeId, toPositionKey } from '../../../utils/triggerNodeIds'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { EdgeType } from '../utils/workflowToGraph'

type UseWorkflowGraphInitParams = {
  workflowId: string | null | undefined
  workflowVersion: number
  initialNodes: NodeType[]
  initialEdges: EdgeType[]
}

type UseWorkflowGraphInitResult = {
  nodes: NodeType[]
  edges: EdgeType[]
  setNodes: Dispatch<SetStateAction<NodeType[]>>
  setEdges: Dispatch<SetStateAction<EdgeType[]>>
  isInitializedRef: RefObject<boolean>
  isDeletingRef: RefObject<boolean>
}

function applyStoredNodePositions(
  nodes: NodeType[],
  positions: Record<string, { x: number; y: number }>,
  triggers: NonNullable<WorkflowDefinition['triggers']>
): NodeType[] {
  if (Object.keys(positions).length === 0) return nodes
  return nodes.map((node) => {
    const stored = positions[toPositionKey(node.id, triggers)]
    return stored ? { ...node, position: stored } : node
  })
}

function edgesMatchWorkflow(
  initialEdges: EdgeType[],
  currentWorkflow: NonNullable<ReturnType<typeof useWorkflowStore.getState>['currentWorkflow']>
): boolean {
  if (initialEdges.length === 0) return true

  const activityIds = collectAllActivityIds(currentWorkflow.workflow.activities)
  const workflowTriggers = currentWorkflow.triggers ?? []
  workflowTriggers.forEach((_: unknown, index: number) => {
    activityIds.add(buildTriggerNodeId(index))
  })

  return initialEdges.every((edge) => {
    const sourceValid = edge.source != null && (activityIds.has(edge.source) || edge.source.startsWith('placeholder-'))
    const targetValid = edge.target != null && (activityIds.has(edge.target) || edge.target.startsWith('placeholder-'))
    return sourceValid && targetValid
  })
}

/**
 * Manages React Flow node/edge state initialization for the workflow builder canvas.
 *
 * Uses controlled state instead of useNodesState/useEdgesState because React Flow's
 * hooks reset state when initialNodes/initialEdges change, which causes ButtonEdges
 * to be lost when workflow store updates trigger initialEdges recomputation.
 */
export function useWorkflowGraphInit({
  workflowId,
  workflowVersion,
  initialNodes,
  initialEdges,
}: UseWorkflowGraphInitParams): UseWorkflowGraphInitResult {
  const isInitializedRef = useRef(false)
  const lastWorkflowIdRef = useRef<string | null>(workflowId ?? null)
  const lastWorkflowVersionRef = useRef<number>(workflowVersion)
  const initialNodesRef = useRef(initialNodes)
  const initialEdgesRef = useRef(initialEdges)

  useEffect(() => {
    initialNodesRef.current = initialNodes
    initialEdgesRef.current = initialEdges
  }, [initialNodes, initialEdges])

  const [nodes, setNodes] = useState<NodeType[]>([])
  const [edges, setEdges] = useState<EdgeType[]>([])
  const isDeletingRef = useRef(false)

  useEffect(() => {
    const currentWorkflow = useWorkflowStore.getState().currentWorkflow
    const workflowIdChanged = workflowId !== lastWorkflowIdRef.current
    const workflowVersionChanged = workflowVersion !== lastWorkflowVersionRef.current
    const workflowCleared = !currentWorkflow && isInitializedRef.current

    if (workflowIdChanged) {
      isInitializedRef.current = false
      setNodes([])
      setEdges([])
      lastWorkflowIdRef.current = workflowId ?? null
      lastWorkflowVersionRef.current = workflowVersion
    } else if (workflowVersionChanged) {
      isInitializedRef.current = false
      const { nodePositions: positions, currentWorkflow: workflow } = useWorkflowStore.getState()
      const trigs = workflow?.triggers ?? []
      const nodesWithPositions = applyStoredNodePositions(initialNodesRef.current, positions, trigs)
      setNodes(nodesWithPositions)
      setEdges(initialEdgesRef.current)
      lastWorkflowVersionRef.current = workflowVersion
    } else if (workflowCleared) {
      isInitializedRef.current = false
      setNodes([])
      setEdges([])
    }
  }, [workflowId, workflowVersion])

  useEffect(() => {
    const currentWorkflow = useWorkflowStore.getState().currentWorkflow
    const hasWorkflow = !!currentWorkflow
    const isCorrectWorkflow = lastWorkflowIdRef.current === workflowId

    const hasActivities = (currentWorkflow?.workflow?.activities?.length ?? 0) > 0
    if (hasWorkflow && hasActivities && initialEdges.length === 0) {
      return
    }

    const edgesValid = !hasWorkflow || initialEdges.length === 0 || edgesMatchWorkflow(initialEdges, currentWorkflow)

    if (
      !isInitializedRef.current &&
      !isDeletingRef.current &&
      hasWorkflow &&
      isCorrectWorkflow &&
      initialNodes.length > 0 &&
      edgesValid
    ) {
      const positions = useWorkflowStore.getState().nodePositions
      const trigs = currentWorkflow?.triggers ?? []
      const nodesWithPositions = applyStoredNodePositions(initialNodes, positions, trigs)

      setNodes(nodesWithPositions)
      setEdges(initialEdges)
      isInitializedRef.current = true
    }
  }, [initialNodes, initialEdges, workflowId, workflowVersion])

  return {
    nodes,
    edges,
    setNodes,
    setEdges,
    isInitializedRef,
    isDeletingRef,
  }
}

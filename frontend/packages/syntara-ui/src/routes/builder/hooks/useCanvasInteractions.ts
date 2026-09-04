import { applyEdgeChanges, applyNodeChanges, type Connection, type EdgeChange, type NodeChange } from '@xyflow/react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { detachPromise } from '../../../utils/detachPromise'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { PendingEdge } from '../types'
import { validateConnection } from '../utils/validateConnection'
import type { EdgeType } from '../utils/workflowToGraph'

import { useExternalNodeSelection } from './useExternalNodeSelection'

function resolvePendingEdge(
  pendingEdge: PendingEdge | null,
  panelOpen: boolean | undefined,
  nodes: NodeType[]
): PendingEdge | null {
  if (!pendingEdge) return null
  if (!panelOpen) return null
  const sourceExists = nodes.some((node) => node.id === pendingEdge.sourceNodeId)
  if (!sourceExists) return null
  return pendingEdge
}

type UseCanvasInteractionsParams = {
  isReadOnly: boolean
  edges: EdgeType[]
  nodes: NodeType[]
  panelOpen?: boolean
  fitView: (options?: { duration?: number; padding?: number }) => Promise<boolean>
  isInitialized: boolean
  selectedActivityId?: string | null
  setNodes: React.Dispatch<React.SetStateAction<NodeType[]>>
  setEdges: React.Dispatch<React.SetStateAction<EdgeType[]>>
}

type UseCanvasInteractionsResult = {
  onNodesChange: (changes: NodeChange<NodeType>[]) => void
  onEdgesChange: (changes: EdgeChange<EdgeType>[]) => void
  pendingEdge: PendingEdge | null
  setPendingEdge: React.Dispatch<React.SetStateAction<PendingEdge | null>>
  isValidConnection: (connection: EdgeType | Connection) => boolean
}

/**
 * Canvas-level React Flow interaction handlers: node/edge change callbacks,
 * pending edge state, external selection sync, and fit-view on panel toggle.
 */
export function useCanvasInteractions({
  isReadOnly,
  edges,
  nodes,
  panelOpen,
  fitView,
  isInitialized,
  selectedActivityId,
  setNodes,
  setEdges,
}: UseCanvasInteractionsParams): UseCanvasInteractionsResult {
  const [pendingEdge, setPendingEdge] = useState<PendingEdge | null>(null)

  const resolvedPendingEdge = useMemo(
    () => resolvePendingEdge(pendingEdge, panelOpen, nodes),
    [pendingEdge, panelOpen, nodes]
  )

  useEffect(() => {
    if (pendingEdge !== null && resolvedPendingEdge === null) {
      setPendingEdge(null)
    }
  }, [pendingEdge, resolvedPendingEdge])

  const onNodesChange = useCallback(
    (changes: NodeChange<NodeType>[]) => {
      const filtered = isReadOnly
        ? changes.filter(
            (change) => change.type === 'dimensions' || change.type === 'position' || change.type === 'select'
          )
        : changes
      setNodes((currentNodes) => applyNodeChanges(filtered, currentNodes))
    },
    [isReadOnly, setNodes]
  )

  const onEdgesChange = useCallback(
    (changes: EdgeChange<EdgeType>[]) => {
      if (isReadOnly) return
      setEdges((currentEdges) => applyEdgeChanges(changes, currentEdges))
    },
    [isReadOnly, setEdges]
  )

  useExternalNodeSelection(selectedActivityId, setNodes)

  useEffect(() => {
    if (isInitialized) {
      const timer = setTimeout(() => {
        detachPromise(fitView({ duration: 300, padding: 0.1 }))
      }, 100)
      return () => clearTimeout(timer)
    }
  }, [panelOpen, fitView, isInitialized])

  const isValidConnection = useCallback(
    (connection: EdgeType | Connection) => validateConnection(connection, edges),
    [edges]
  )

  return {
    onNodesChange,
    onEdgesChange,
    pendingEdge: resolvedPendingEdge,
    setPendingEdge,
    isValidConnection,
  }
}

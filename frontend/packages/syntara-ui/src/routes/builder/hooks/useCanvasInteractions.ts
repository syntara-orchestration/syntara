import { applyEdgeChanges, applyNodeChanges, type Connection, type EdgeChange, type NodeChange } from '@xyflow/react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { FlowNodeType } from '../../../constants'
import { detachPromise } from '../../../utils/detachPromise'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { PendingEdge } from '../types'
import { isButtonEdge } from '../utils/filterHelpers'
import { validateConnection } from '../utils/validateConnection'
import type { EdgeType } from '../utils/workflowToGraph'

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

const NODE_PROJECTION_DATA_KEYS = ['__executionState', '__validationError']
const NODE_PROJECTION_METADATA_KEYS = ['__mockDataPinned', '__reverseHandles', '__showExecutionBadge']
const EDGE_PROJECTION_DATA_KEYS = ['executionStatus', 'isActive', 'onAddNode']

function isSyntheticNode(node: NodeType): boolean {
  return (
    node.id.startsWith('placeholder-') ||
    node.id.startsWith('pending-target-') ||
    node.type === FlowNodeType.PLACEHOLDER
  )
}

function isSyntheticEdge(edge: EdgeType): boolean {
  return isButtonEdge(edge) || edge.id.startsWith('pending-')
}

function stripButtonEdgeClasses(className: string | undefined): string | undefined {
  if (!className) return className
  const remaining = className
    .split(/\s+/)
    .filter((classToken) => classToken !== 'has-button-edge' && !/^handle-.+-connected$/.test(classToken))
    .join(' ')
  return remaining || undefined
}

function copyRawProjectionFields(
  incoming: Record<string, unknown>,
  raw: Record<string, unknown> | undefined,
  keys: string[]
): Record<string, unknown> {
  const result = { ...incoming }
  for (const key of keys) {
    if (raw && Object.hasOwn(raw, key)) result[key] = raw[key]
    else delete result[key]
  }
  return result
}

function withoutNodeProjectionFields(item: NodeType, rawNode?: NodeType): NodeType {
  const itemData = item.data as Record<string, unknown>
  const rawData = rawNode?.data
  const data = copyRawProjectionFields(itemData, rawData, NODE_PROJECTION_DATA_KEYS)
  const itemMetadata = itemData.metadata as Record<string, unknown> | undefined
  const rawMetadata =
    rawData && 'metadata' in rawData && typeof rawData.metadata === 'object' && rawData.metadata !== null
      ? (rawData.metadata as Record<string, unknown>)
      : undefined
  if (itemMetadata) {
    const metadata = copyRawProjectionFields(itemMetadata, rawMetadata, NODE_PROJECTION_METADATA_KEYS)
    if (Object.keys(metadata).length > 0 || rawMetadata) data.metadata = metadata
    else delete data.metadata
  }

  const itemIsTask = item.type === FlowNodeType.TASK || item.type === FlowNodeType.TASK_REVERSED
  const rawIsTask = rawNode?.type === FlowNodeType.TASK || rawNode?.type === FlowNodeType.TASK_REVERSED
  const type = rawNode && itemIsTask && rawIsTask ? rawNode.type : item.type
  const normalizedType = !rawNode && item.type === FlowNodeType.TASK_REVERSED ? FlowNodeType.TASK : type

  return {
    ...item,
    ...(rawNode ? { selected: rawNode.selected } : {}),
    type: normalizedType,
    className: stripButtonEdgeClasses(item.className),
    data,
  } as NodeType
}

function withoutEdgeProjectionFields(item: EdgeType, rawEdge?: EdgeType): EdgeType {
  const itemData = item.data
  const rawData = rawEdge?.data
  let data = itemData
  if (itemData) {
    data = copyRawProjectionFields(itemData, rawData, EDGE_PROJECTION_DATA_KEYS)
    if (Object.keys(data).length === 0 && rawEdge?.data === undefined) data = undefined
  }

  return {
    ...item,
    markerEnd: rawEdge?.markerEnd,
    data,
  }
}

function removeProjectedNodeFields(changes: NodeChange<NodeType>[], currentNodes: NodeType[]): NodeChange<NodeType>[] {
  return changes
    .filter((change) => {
      if (change.type === 'add' || change.type === 'replace') return !isSyntheticNode(change.item)
      return !change.id.startsWith('placeholder-') && !change.id.startsWith('pending-target-')
    })
    .map((change) => {
      if (change.type !== 'add' && change.type !== 'replace') return change
      const rawNode = change.type === 'replace' ? currentNodes.find((node) => node.id === change.id) : undefined
      return { ...change, item: withoutNodeProjectionFields(change.item, rawNode) }
    })
}

function removeProjectedEdgeFields(changes: EdgeChange<EdgeType>[], currentEdges: EdgeType[]): EdgeChange<EdgeType>[] {
  return changes
    .filter((change) => {
      if (change.type === 'add' || change.type === 'replace') return !isSyntheticEdge(change.item)
      return !change.id.startsWith('button-') && !change.id.startsWith('pending-')
    })
    .map((change) => {
      if (change.type !== 'add' && change.type !== 'replace') return change
      const rawEdge = change.type === 'replace' ? currentEdges.find((edge) => edge.id === change.id) : undefined
      return { ...change, item: withoutEdgeProjectionFields(change.item, rawEdge) }
    })
}

type UseCanvasInteractionsParams = {
  isReadOnly: boolean
  edges: EdgeType[]
  nodes: NodeType[]
  panelOpen?: boolean
  fitView: (options?: { duration?: number; padding?: number }) => Promise<boolean>
  isInitialized: boolean
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
 * pending edge state and fit-view on panel toggle.
 */
export function useCanvasInteractions({
  isReadOnly,
  edges,
  nodes,
  panelOpen,
  fitView,
  isInitialized,
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
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync stale pending edge when panel closes or source node is removed
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
      setNodes((currentNodes) => applyNodeChanges(removeProjectedNodeFields(filtered, currentNodes), currentNodes))
    },
    [isReadOnly, setNodes]
  )

  const onEdgesChange = useCallback(
    (changes: EdgeChange<EdgeType>[]) => {
      if (isReadOnly) return
      setEdges((currentEdges) => applyEdgeChanges(removeProjectedEdgeFields(changes, currentEdges), currentEdges))
    },
    [isReadOnly, setEdges]
  )

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

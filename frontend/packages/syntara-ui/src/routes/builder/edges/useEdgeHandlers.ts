import type { MarkerType } from '@xyflow/react'
import { useReactFlow } from '@xyflow/react'
import { useCallback } from 'react'

import { getEffectiveMarkerEnd } from './edgeMarkerHelpers'
import type { EdgeData } from './types'
import { useEdgeHover, useEdgeSourceHandle } from './useEdgeHover'

type UseEdgeHandlersProps = {
  edgeId: string
  source: string
  target: string
  markerEnd?: string | { type: MarkerType; width: number; height: number; color: string }
  selected?: boolean
  data?: EdgeData
}

/**
 * Shared hook that provides all common edge functionality:
 * - Hover state management
 * - Marker end calculation
 * - Delete and add step handlers
 */
export function useEdgeHandlers(props: UseEdgeHandlersProps) {
  const { edgeId, source, target, markerEnd, selected, data } = props
  const reactFlowInstance = useReactFlow()
  const { setEdges } = reactFlowInstance

  const actualSourceHandle = useEdgeSourceHandle(edgeId)
  const {
    isHovered,
    isEdgeHovered,
    handleEdgeMouseEnter,
    handleEdgeMouseLeave,
    handleButtonMouseEnter,
    handleButtonMouseLeave,
  } = useEdgeHover()

  // Convert markerEnd to string if it's already a string, otherwise pass undefined
  // (React Flow marker objects can't be converted to our custom marker URLs)
  // Note: Pending edges are handled directly in EdgePath component
  const markerEndString = typeof markerEnd === 'string' ? markerEnd : undefined
  const effectiveMarkerEnd = getEffectiveMarkerEnd(selected, isEdgeHovered, data?.isActive, markerEndString)

  const handleDelete = useCallback(
    (event: React.MouseEvent) => {
      event.stopPropagation()
      setEdges((edges) => edges.filter((edge) => edge.id !== edgeId))
    },
    [edgeId, setEdges]
  )

  const handleAddNode = useCallback(
    (event: React.MouseEvent) => {
      event.stopPropagation()
      data?.onAddNode?.({
        sourceNodeId: source,
        targetNodeId: target,
        edgeId,
        sourceHandle: actualSourceHandle ?? undefined,
      })
    },
    [data, source, target, edgeId, actualSourceHandle]
  )

  return {
    isHovered,
    isEdgeHovered,
    effectiveMarkerEnd,
    handleEdgeMouseEnter,
    handleEdgeMouseLeave,
    handleButtonMouseEnter,
    handleButtonMouseLeave,
    handleDelete,
    handleAddNode,
  }
}

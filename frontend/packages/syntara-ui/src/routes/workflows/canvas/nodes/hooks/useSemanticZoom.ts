import type { ReactFlowState } from '@xyflow/react'
import { useStore, useUpdateNodeInternals } from '@xyflow/react'
import { useCallback, useLayoutEffect, useRef } from 'react'

import { SEMANTIC_ZOOM_MAX_SCALE } from '../../semanticZoom'

/**
 * Whether the canvas is in semantic-zoom LOD for this node. Uses {@link useStore} with a boolean
 * selector so nodes re-render when zoom crosses {@link SEMANTIC_ZOOM_MAX_SCALE}, not on every pan frame.
 */
export function useSemanticZoom(nodeId: string, hasSemanticZoomSummary: boolean): boolean {
  const updateNodeInternals = useUpdateNodeInternals()

  const isSemanticZoom = useStore(
    useCallback(
      (s: ReactFlowState) => hasSemanticZoomSummary && s.transform[2] <= SEMANTIC_ZOOM_MAX_SCALE,
      [hasSemanticZoomSummary]
    )
  )

  const prevSemanticZoomRef = useRef<boolean | undefined>(undefined)

  useLayoutEffect(() => {
    if (!hasSemanticZoomSummary) return

    const prev = prevSemanticZoomRef.current
    if (prev === undefined) {
      prevSemanticZoomRef.current = isSemanticZoom
      // Avoid updateNodeInternals on first paint at default zoom — it triggers xyflow layout
      // in happy-dom (DOMMatrixReadOnly). Only measure when the user already has semantic zoom.
      if (isSemanticZoom) {
        updateNodeInternals(nodeId)
      }
      return
    }

    if (prev !== isSemanticZoom) {
      prevSemanticZoomRef.current = isSemanticZoom
      updateNodeInternals(nodeId)
    }
  }, [isSemanticZoom, nodeId, hasSemanticZoomSummary, updateNodeInternals])

  return isSemanticZoom
}

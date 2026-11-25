import type { ReactFlowState } from '@xyflow/react'
import { useStore } from '@xyflow/react'
import { useCallback } from 'react'

import { SEMANTIC_ZOOM_MAX_SCALE } from '../../semanticZoom'

/**
 * Whether the canvas is in semantic-zoom LOD for this node. Uses {@link useStore} with a boolean
 * selector so nodes re-render when zoom crosses {@link SEMANTIC_ZOOM_MAX_SCALE}, not on every pan frame.
 */
export function useSemanticZoom(hasSemanticZoomSummary: boolean): boolean {
  return useStore(
    useCallback(
      (s: ReactFlowState) => hasSemanticZoomSummary && s.transform[2] <= SEMANTIC_ZOOM_MAX_SCALE,
      [hasSemanticZoomSummary]
    )
  )
}

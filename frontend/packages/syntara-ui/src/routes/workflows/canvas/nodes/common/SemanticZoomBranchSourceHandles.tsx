import { Handle, Position } from '@xyflow/react'

import type { SemanticZoomBranchSource } from '../../semanticZoomTypes'

import { sourceHandleStyle } from './handleStyle'

export type { SemanticZoomBranchSource } from '../../semanticZoomTypes'

/**
 * Source handles for branching nodes at semantic zoom: no labels, stacked on the
 * right edge of the icon tile so edges fan out (matches topology-style LOD).
 */
export function SemanticZoomBranchSourceHandles(props: { handles: readonly SemanticZoomBranchSource[] }) {
  const { handles } = props
  const n = handles.length
  if (n === 0) return null

  return (
    <>
      {handles.map((h, i) => {
        const topPercent = (100 * (i + 1)) / (n + 1)
        return (
          <Handle
            key={h.id}
            type="source"
            id={h.id}
            position={Position.Right}
            aria-label={h.ariaLabel}
            style={{
              ...sourceHandleStyle,
              top: `${topPercent}%`,
            }}
          />
        )
      })}
    </>
  )
}

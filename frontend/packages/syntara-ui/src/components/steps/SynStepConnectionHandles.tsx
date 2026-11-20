import { Handle, Position } from '@xyflow/react'
import type { CSSProperties } from 'react'

import { sourceHandleStyle, targetHandleStyle } from '../../routes/workflows/canvas/nodes/common/handleStyle'

export type SynStepConnectionHandlesProps = {
  isSemanticZoom: boolean
  /** Vertical anchor for semantic-zoom handles (tile center when the node is tile-sized). */
  semanticZoomHandleTop: CSSProperties['top']
  disableTarget?: boolean
  disableSource?: boolean
  enableStart?: boolean
  enableEnd?: boolean
  reverseHandles?: boolean
}

function semanticZoomHandleStyle(
  base: CSSProperties,
  side: 'left' | 'right',
  top: CSSProperties['top']
): CSSProperties {
  return {
    ...base,
    top,
    transform: side === 'left' ? 'translate(-50%, -50%)' : 'translate(50%, -50%)',
  }
}

export function SynStepConnectionHandles(props: Readonly<SynStepConnectionHandlesProps>) {
  const withSemanticZoom = (base: CSSProperties, side: 'left' | 'right') =>
    props.isSemanticZoom ? semanticZoomHandleStyle(base, side, props.semanticZoomHandleTop) : base

  const targetSide = props.reverseHandles ? 'right' : 'left'
  const sourceSide = props.reverseHandles ? 'left' : 'right'

  return (
    <>
      {!props.disableTarget && (
        <Handle
          type="target"
          id="target"
          position={props.reverseHandles ? Position.Right : Position.Left}
          style={withSemanticZoom(targetHandleStyle, targetSide)}
        />
      )}
      {!props.disableSource && (
        <Handle
          type="source"
          id="source"
          position={props.reverseHandles ? Position.Left : Position.Right}
          style={withSemanticZoom(sourceHandleStyle, sourceSide)}
        />
      )}
      {props.enableStart && (
        <Handle
          type="source"
          id="start"
          position={Position.Right}
          style={{
            ...withSemanticZoom(sourceHandleStyle, 'right'),
            top: '85%',
          }}
        />
      )}
      {props.enableEnd && (
        <Handle
          type="target"
          id="end"
          position={Position.Left}
          style={{
            ...withSemanticZoom(targetHandleStyle, 'left'),
            top: props.isSemanticZoom ? props.semanticZoomHandleTop : '50%',
            opacity: 0,
            pointerEvents: 'none',
          }}
        />
      )}
    </>
  )
}

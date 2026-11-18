import { Icon } from '@patternfly/react-core'
import { RhUiAddSquareIcon } from '@patternfly/react-icons'
import { BaseEdge, EdgeLabelRenderer, useReactFlow } from '@xyflow/react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { setPendingDragHandle } from '../utils/pendingDragHandle'
import { useIsVersionView } from '../VersionViewContext'

import { BUTTON_EDGE_DEFAULT_STROKE, getButtonEdgeStrokeColor } from './buttonEdgeStrokeColor'
import { adjustSourceCoordinates, calculateStubTarget } from './edgeUtils'
import type { ButtonEdgeProps } from './types'

const STUB_LENGTH = 50

/** Size of the "+" square container in pixels */
const PLUS_BUTTON_SIZE = 24
const PLUS_BUTTON_HALF = PLUS_BUTTON_SIZE / 2
const PLUS_BUTTON_BORDER_RADIUS = 'var(--pf-t--global--border--radius--small)'

function useButtonEdgeDragHandler(params: { id: string; source: string; sourceX: number; sourceY: number }) {
  const reactFlowInstance = useReactFlow()
  const [isDragging, setIsDragging] = useState(false)
  const mouseUpHandlerRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    return () => {
      if (mouseUpHandlerRef.current) {
        document.removeEventListener('mouseup', mouseUpHandlerRef.current)
      }
    }
  }, [])

  const handleMouseDown = useCallback(
    (event: React.MouseEvent) => {
      const sourceNode = reactFlowInstance.getNode(params.source)
      if (!sourceNode) return

      const fullEdge = reactFlowInstance.getEdge(params.id)
      const handleId = fullEdge?.sourceHandle || 'source'
      const handleElement = document.querySelector(`[data-nodeid="${params.source}"][data-handleid="${handleId}"]`)
      if (!handleElement) return

      setPendingDragHandle(params.source, handleId)
      const screenPosition = reactFlowInstance.flowToScreenPosition({
        x: params.sourceX,
        y: params.sourceY,
      })
      const syntheticEvent = new MouseEvent('mousedown', {
        bubbles: true,
        cancelable: true,
        clientX: screenPosition.x,
        clientY: screenPosition.y,
        button: 0,
      })

      setIsDragging(true)
      handleElement.dispatchEvent(syntheticEvent)

      const handleMouseUp = () => {
        setIsDragging(false)
        mouseUpHandlerRef.current = null
        document.removeEventListener('mouseup', handleMouseUp)
      }
      mouseUpHandlerRef.current = handleMouseUp
      document.addEventListener('mouseup', handleMouseUp)

      event.preventDefault()
      event.stopPropagation()
    },
    [params.id, params.source, params.sourceX, params.sourceY, reactFlowInstance]
  )

  return { handleMouseDown, isDragging }
}

/**
 * Edge with a plus button that opens the add step panel
 * Used for adding new steps connected to existing steps
 * Creates a short stub edge extending from the source node
 */
export function ButtonEdge(props: ButtonEdgeProps) {
  const { sourceX, sourceY, sourcePosition, style, data, id, source, sourceHandleId } = props
  const [isFocused, setIsFocused] = useState(false)
  const { handleMouseDown, isDragging } = useButtonEdgeDragHandler({ id, source, sourceX, sourceY })
  const isVersionView = useIsVersionView()

  if (isVersionView) return null

  const strokeColor = getButtonEdgeStrokeColor(sourceHandleId ?? data?.sourceHandle)

  const { x: adjustedSourceX, y: adjustedSourceY } = adjustSourceCoordinates(sourceX, sourceY, sourcePosition)
  const { targetX: buttonX, targetY: buttonY } = calculateStubTarget(
    adjustedSourceX,
    adjustedSourceY,
    sourcePosition,
    STUB_LENGTH
  )
  // All source handles in the builder use Position.Right (left-to-right layout).
  // Stop the line at the left border of the "+" square, not at its center.
  const lineEndX = buttonX - PLUS_BUTTON_HALF
  const edgePath = `M ${adjustedSourceX},${adjustedSourceY} L ${lineEndX},${buttonY}`

  const handleClick = (event: React.SyntheticEvent) => {
    event.stopPropagation()
    if (!isDragging) {
      data?.onButtonClick?.({ x: buttonX, y: buttonY })
    }
  }

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      handleClick(event)
    }
  }

  // When dragging, use inline styles to override CSS that hides button edges during connection
  const draggingStyle = isDragging ? { opacity: 1 } : undefined

  return (
    <>
      {/* Main edge — wide invisible path for easy hit detection */}
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          ...style,
          stroke: BUTTON_EDGE_DEFAULT_STROKE,
          strokeWidth: 20,
          opacity: 0.01,
        }}
        markerEnd={undefined}
      />
      {/* Visible thin stroke — no arrow marker; colored for approval handles */}
      <path
        data-testid="button-edge-stroke"
        d={edgePath}
        fill="none"
        stroke={strokeColor}
        strokeWidth={2}
        pointerEvents="none"
        style={draggingStyle}
      />
      {/* Plus button — rounded square with "+" icon (non-interactive visual) */}
      <EdgeLabelRenderer>
        <div
          className="button-edge-plus"
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${buttonX}px,${buttonY}px)`,
            pointerEvents: 'none',
            width: PLUS_BUTTON_SIZE,
            height: PLUS_BUTTON_SIZE,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: PLUS_BUTTON_BORDER_RADIUS,
            border: `1px solid var(--pf-t--global--border--color--default)`,
            backgroundColor: 'var(--pf-t--global--background--color--primary--default)',
            color: data?.isActive
              ? 'var(--pf-t--global--icon--color--regular)'
              : 'var(--pf-t--global--icon--color--subtle)',
            ...draggingStyle,
          }}
        >
          <Icon iconSize="md">
            <RhUiAddSquareIcon />
          </Icon>
        </div>
      </EdgeLabelRenderer>
      {/* Large clickable area (draggable for all canvas step types) */}
      <rect
        x={buttonX - PLUS_BUTTON_HALF}
        y={buttonY - PLUS_BUTTON_HALF}
        width={PLUS_BUTTON_SIZE}
        height={PLUS_BUTTON_SIZE}
        fill="transparent"
        rx={4}
        onClick={handleClick}
        onMouseDown={handleMouseDown}
        onKeyDown={handleKeyDown}
        onFocus={() => setIsFocused(true)}
        onBlur={() => setIsFocused(false)}
        role="button"
        aria-label="Add connected step"
        data-testid={sourceHandleId ? `add-node-button-${sourceHandleId}` : undefined}
        tabIndex={-1}
        stroke={isFocused ? 'var(--pf-t--global--color--brand--default)' : 'none'}
        strokeWidth={isFocused ? 2 : 0}
        style={{ cursor: 'pointer', pointerEvents: 'all', zIndex: 100 }}
      />
    </>
  )
}

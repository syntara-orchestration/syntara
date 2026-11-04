import { EdgeHandleEnum } from '@syntara/contracts'
import type { EdgeProps, MarkerType } from '@xyflow/react'
import { BaseEdge } from '@xyflow/react'
import { useMemo } from 'react'

import { useIsStepFormReadOnly } from '../VersionViewContext'

import { BUTTON_EDGE_DEFAULT_STROKE, CANVAS_EDGE_HIGHLIGHT_STROKE } from './buttonEdgeStrokeColor'
import { EDGE_INTERACTION_DROP_SHADOW } from './edgeInteractionStyles'

/** PatternFly tokens for approval branch edge stroke/marker */
const APPROVED_EDGE_COLOR = 'var(--pf-t--global--color--status--success--default)'
const REJECTED_EDGE_COLOR = 'var(--pf-t--global--color--status--danger--default)'

type EdgePathProps = {
  /** The SVG path string for the edge */
  edgePath: string
  /** The marker end for the edge (string URL or React Flow marker object) */
  markerEnd?: string | { type: MarkerType; width: number; height: number; color: string }
  /** Additional style to merge with default edge styles */
  style?: React.CSSProperties
  /** Whether the edge is selected */
  selected?: boolean
  /** Whether the edge is hovered */
  isEdgeHovered: boolean
  /** Edge data containing isActive, isPending, and executionStatus */
  data?: {
    isActive?: boolean
    isPending?: boolean
    executionStatus?: 'passed' | 'pending'
  }
  /** Source handle id; when 'approved' or 'rejected', edge is colored to match the approval result */
  sourceHandle?: string | null
  /** Mouse enter handler for hover detection */
  onMouseEnter: () => void
  /** Mouse leave handler for hover detection */
  onMouseLeave: () => void
}

/**
 * Shared edge path rendering component
 * Renders both the visible BaseEdge and the invisible hover detection path
 */
export function EdgePath(props: EdgePathProps) {
  const { edgePath, markerEnd, style, selected, isEdgeHovered, data, sourceHandle, onMouseEnter, onMouseLeave } = props
  const isReadOnly = useIsStepFormReadOnly()

  // Determine stroke color and style: execution status > approval handle > interactive state > default
  const { strokeColor, strokeOpacity, strokeDasharray } = useMemo(() => {
    // Execution status takes precedence over interactive states and approval handle
    if (data?.executionStatus === 'passed') {
      return {
        strokeColor: BUTTON_EDGE_DEFAULT_STROKE,
        strokeOpacity: 1,
        strokeDasharray: 'none',
      }
    }
    if (data?.executionStatus === 'pending') {
      return {
        strokeColor: BUTTON_EDGE_DEFAULT_STROKE,
        strokeOpacity: 1,
        strokeDasharray: '5,5',
      }
    }

    // Approval branch edges: color by result (approved = green, rejected = red)
    if (sourceHandle === EdgeHandleEnum.APPROVED) {
      return {
        strokeColor: APPROVED_EDGE_COLOR,
        strokeOpacity: 1,
        strokeDasharray: 'none',
      }
    }
    if (sourceHandle === EdgeHandleEnum.REJECTED) {
      return {
        strokeColor: REJECTED_EDGE_COLOR,
        strokeOpacity: 1,
        strokeDasharray: 'none',
      }
    }

    // Fall back to existing interactive state styling
    const isHighlighted = selected || isEdgeHovered || data?.isActive
    return {
      strokeColor: isHighlighted ? CANVAS_EDGE_HIGHLIGHT_STROKE : BUTTON_EDGE_DEFAULT_STROKE,
      strokeOpacity: 1,
      strokeDasharray: 'none',
    }
  }, [selected, isEdgeHovered, data?.isActive, data?.executionStatus, sourceHandle])

  // Use stroke color for marker when edge is approval-colored so the arrow matches
  const effectiveMarkerEnd =
    typeof markerEnd === 'object' &&
    markerEnd != null &&
    (sourceHandle === EdgeHandleEnum.APPROVED || sourceHandle === EdgeHandleEnum.REJECTED)
      ? { ...markerEnd, color: strokeColor }
      : markerEnd

  const edgeStyle = {
    ...style,
    stroke: strokeColor,
    strokeOpacity,
    strokeDasharray,
    strokeWidth: 2,
    pointerEvents: 'none' as const,
    filter: selected || isEdgeHovered || data?.isActive ? EDGE_INTERACTION_DROP_SHADOW : 'none',
  }

  return (
    <>
      {/* Visible edge - render path directly for pending edges to use custom marker */}
      {data?.isPending && typeof markerEnd === 'string' ? (
        <g>
          <defs>
            <marker
              id="pending-arrow-marker"
              markerWidth="12"
              markerHeight="12"
              viewBox="-10 -10 20 20"
              orient="auto"
              refX="-5"
              refY="0"
            >
              <polyline
                stroke={strokeColor}
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="1"
                fill={strokeColor}
                points="-5,-4 0,0 -5,4 -5,-4"
              />
            </marker>
          </defs>
          <path
            d={edgePath}
            fill="none"
            stroke={strokeColor}
            strokeWidth={2}
            markerEnd="url(#pending-arrow-marker)"
            style={edgeStyle}
          />
        </g>
      ) : (
        <BaseEdge path={edgePath} markerEnd={effectiveMarkerEnd as EdgeProps['markerEnd']} style={edgeStyle} />
      )}
      {/* Invisible wider path for hover detection */}
      {!data?.isPending && !isReadOnly && (
        <path
          d={edgePath}
          fill="none"
          stroke="transparent"
          strokeWidth={20}
          onMouseEnter={onMouseEnter}
          onMouseLeave={onMouseLeave}
          style={{ pointerEvents: 'stroke' }}
        />
      )}
    </>
  )
}

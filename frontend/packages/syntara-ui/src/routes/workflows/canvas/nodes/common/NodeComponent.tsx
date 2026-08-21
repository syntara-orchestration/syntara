import { Icon, Label } from '@patternfly/react-core'
import { RhUiWarningFillIcon } from '@patternfly/react-icons'
import { ExecutorTypeEnum, type TaskActivity } from '@syntara/contracts'
import { Handle, type NodeProps, Position } from '@xyflow/react'
import React, { useEffect, useMemo, useState } from 'react'

import { SynPanel } from '../../../../../components/layout/SynPanel'
import { FlowNodeType } from '../../../../../constants'
import { ExecutionStatusBadge } from '../../../../builder/components/ExecutionStatusBadge'
import type { ActivityStatus } from '../../../execution/types'
import { NODE_TYPE_COLORS } from '../../nodeTypeColors'
import type { SemanticZoomBranchSource } from '../../semanticZoomTypes'
import { useSemanticZoom } from '../hooks/useSemanticZoom'

import { targetHandleStyle, sourceHandleStyle } from './handleStyle'
import { NodeExpandedAllContext } from './NodeExpandedAllContext'
import { NodeExpandedContext } from './NodeExpandedContext'
import { NodeSemanticZoomBody } from './NodeSemanticZoomBody'

type ExecutionState = {
  status: ActivityStatus
  started_at?: string
  completed_at?: string
  error_details?: string
  retry_count?: number
}

const DEFAULT_NODE_WIDTH = 240
const WIDE_NODE_WIDTH = 360

const NODE_BOTTOM_BADGE_STYLE: React.CSSProperties = {
  position: 'absolute',
  bottom: 'calc(-1 * var(--pf-t--global--spacer--lg))',
  left: '50%',
  transform: 'translateX(-50%)',
  whiteSpace: 'nowrap',
}

/**
 * PatternFly `Panel` with `variant="raised"` uses the raised variant’s smaller corner radius; workflow nodes
 * should visually match `Card` / canvas chrome, which use `--pf-t--global--border--radius--medium`.
 */
const WORKFLOW_NODE_PANEL_RADIUS_STYLE = {
  '--pf-v6-c-panel--BorderRadius': 'var(--pf-t--global--border--radius--medium)',
} as React.CSSProperties

const VALIDATION_BADGE_STYLE: React.CSSProperties = {
  position: 'absolute',
  bottom: '-20px',
  right: '-20px',
  width: '48px',
  height: '48px',
  borderRadius: '50%',
  backgroundColor: 'var(--pf-t--global--background--color--primary--default)',
  borderColor: 'var(--pf-t--global--color--status--warning--default)',
  borderStyle: 'solid',
  borderWidth: '2px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 10,
}

function ValidationErrorBadge() {
  return (
    <div
      data-testid="validation-error-badge"
      style={VALIDATION_BADGE_STYLE}
      title="Verification error"
      role="img"
      aria-label="Verification error"
    >
      <Icon size="xl">
        <RhUiWarningFillIcon style={{ color: 'var(--pf-t--global--color--status--warning--default)' }} />
      </Icon>
    </div>
  )
}

const isWideTaskNode = (nodeProps: NodeProps) => {
  if (nodeProps.type === FlowNodeType.GENERIC) {
    return true
  }

  if (nodeProps.type !== FlowNodeType.TASK && nodeProps.type !== FlowNodeType.TASK_REVERSED) {
    return false
  }

  const data = nodeProps.data as TaskActivity | undefined
  if (!data) return false

  // In v2, activity.type IS the executor directly (no task.executor wrapper)
  if (data.type === ExecutorTypeEnum.AGENTIC) {
    return true
  }

  return false
}

// eslint-disable-next-line complexity
export function NodeComponent(props: {
  children: React.ReactNode
  disableSource?: boolean
  disableTarget?: boolean
  enableStart?: boolean
  enableEnd?: boolean
  reverseHandles?: boolean
  className?: string
  style?: React.CSSProperties
  hasDashedBorder?: boolean
  onClick?: (e: React.MouseEvent<HTMLDivElement, MouseEvent>) => void
  nodeProps: NodeProps
  collapsible?: boolean
  executionState?: ExecutionState
  showExecutionBadge?: boolean
  /** Optional color for the type indicator bar at the top of the node (PatternFly token or CSS color) */
  topBarColor?: string
  /** When zoomed out, used for tooltip text on the compact color block */
  semanticZoomSummary?: { title: string; typeLabel: string }
  /** Branch source handles at semantic zoom (no labels; stacked on the bar edge) */
  semanticZoomBranchSources?: readonly SemanticZoomBranchSource[]
  /** Optional stable hook for tests (e.g. canvas node root) */
  rootTestId?: string
}) {
  const { expandAllEvent, collapseAllEvent } = React.use(NodeExpandedAllContext)
  const expandedContext = useState(true)
  const isCollapsible = props.collapsible ?? true

  const hasSemanticZoomSummary = props.semanticZoomSummary !== undefined
  const isSemanticZoom = useSemanticZoom(props.nodeProps.id, hasSemanticZoomSummary)

  const semanticFillColor = props.topBarColor ?? NODE_TYPE_COLORS.generic

  const barRadiusStyle = useMemo(() => {
    const s = props.style
    if (!s) return undefined
    return {
      borderRadius: s.borderRadius,
      borderTopLeftRadius: s.borderTopLeftRadius,
      borderBottomLeftRadius: s.borderBottomLeftRadius,
    }
  }, [props.style])

  useEffect(() => {
    if (!isCollapsible) return

    const expandListener = () => {
      expandedContext[1](true)
    }
    const collapseListener = () => {
      expandedContext[1](false)
    }
    expandAllEvent.addEventListener('expandAll', expandListener)
    collapseAllEvent.addEventListener('collapseAll', collapseListener)
    return () => {
      expandAllEvent.removeEventListener('expandAll', expandListener)
      collapseAllEvent.removeEventListener('collapseAll', collapseListener)
    }
  }, [expandAllEvent, collapseAllEvent, expandedContext, isCollapsible])

  const isSelected = props.nodeProps.selected
  const nodeWidth = isWideTaskNode(props.nodeProps) ? WIDE_NODE_WIDTH : DEFAULT_NODE_WIDTH
  const summary = props.semanticZoomSummary
  const mockDataPinned =
    (props.nodeProps.data as { metadata?: { __mockDataPinned?: boolean } }).metadata?.__mockDataPinned === true
  const hasValidationError = props.nodeProps.data.__validationError === true
  const isDisabled = (props.nodeProps.data as { settings?: { disabled?: boolean } }).settings?.disabled === true

  const panelStyle: React.CSSProperties = {
    overflow: 'visible', // Allow execution badge to overflow outside node
    cursor: props.onClick || props.hasDashedBorder ? 'pointer' : undefined,
    width: `${nodeWidth}px`, // Fixed width for consistent node sizing
    minWidth: `${nodeWidth}px`,
    maxWidth: `${nodeWidth}px`,
    ...WORKFLOW_NODE_PANEL_RADIUS_STYLE,
    ...(isSemanticZoom
      ? {
          borderWidth: 0,
          ...props.style,
        }
      : {
          // Type indicator: top border in type color (structural, always present — not conditional on
          // selection so the border geometry stays fixed and toggling selection causes no layout shift).
          ...(props.topBarColor &&
            !props.hasDashedBorder && {
              borderTopWidth: 4,
              borderTopStyle: 'solid' as const,
              borderTopColor: props.topBarColor,
              borderRightWidth: 0,
              borderBottomWidth: 0,
              borderLeftWidth: 0,
            }),
          // Dashed placeholder (e.g. GenericNode): full dashed border, no type-colored top bar.
          ...(props.hasDashedBorder &&
            !isSelected && {
              borderWidth: 2,
              borderStyle: 'dashed' as const,
              borderColor: 'rgba(196, 181, 253, 0.5)',
            }),
          // Dashed selected: color change only — width stays 2px so no layout shift.
          ...(isSelected &&
            props.hasDashedBorder && {
              borderWidth: 2,
              borderStyle: 'dashed' as const,
              borderColor: 'var(--pf-t--global--color--brand--default)',
            }),
          // Normal selected: outline instead of a full border swap — doesn't affect box model.
          ...(isSelected &&
            !props.hasDashedBorder && {
              outline: '2px solid var(--pf-t--global--color--brand--default)',
              outlineOffset: -2,
            }),
          // Disabled node: dashed gray border + reduced opacity (matches skipped execution state).
          ...(isDisabled && {
            borderTopWidth: 2,
            borderTopStyle: 'dashed' as const,
            borderTopColor: 'var(--pf-t--global--color--nonstatus--gray--default)',
            borderRightWidth: 2,
            borderRightStyle: 'dashed' as const,
            borderRightColor: 'var(--pf-t--global--color--nonstatus--gray--default)',
            borderBottomWidth: 2,
            borderBottomStyle: 'dashed' as const,
            borderBottomColor: 'var(--pf-t--global--color--nonstatus--gray--default)',
            borderLeftWidth: 2,
            borderLeftStyle: 'dashed' as const,
            borderLeftColor: 'var(--pf-t--global--color--nonstatus--gray--default)',
            opacity: 0.5,
          }),
          ...props.style,
        }),
  }

  return (
    <NodeExpandedContext.Provider value={expandedContext}>
      <SynPanel
        hasNoPadding
        variant="raised"
        className={props.className}
        data-testid={props.rootTestId}
        onClick={props.onClick}
        style={panelStyle}
        onKeyDown={(e: React.KeyboardEvent) => {
          if (props.onClick && (e.key === 'Enter' || e.key === ' ')) {
            e.preventDefault()
            props.onClick(e as unknown as React.MouseEvent<HTMLDivElement, MouseEvent>)
          }
        }}
        role={props.onClick ? 'button' : undefined}
        tabIndex={props.onClick ? 0 : undefined}
      >
        {isSemanticZoom && summary ? (
          <NodeSemanticZoomBody
            title={summary.title}
            typeLabel={summary.typeLabel}
            backgroundColor={semanticFillColor}
            branchSources={props.semanticZoomBranchSources}
            selected={isSelected}
            hasDashedBorder={props.hasDashedBorder ?? false}
            barStyle={barRadiusStyle}
          />
        ) : (
          props.children
        )}
        {!isSemanticZoom && props.showExecutionBadge !== false && props.executionState && (
          <ExecutionStatusBadge
            status={props.executionState?.status ?? 'pending'}
            retryCount={props.executionState?.retry_count}
            nodeType={props.nodeProps.type}
          />
        )}
        {!isSemanticZoom && mockDataPinned && (
          <div style={NODE_BOTTOM_BADGE_STYLE}>
            <Label isCompact color="purple">
              Mock data pinned
            </Label>
          </div>
        )}
        {!isSemanticZoom && hasValidationError && <ValidationErrorBadge />}
        {!props.disableTarget && (
          <Handle
            type="target"
            id="target"
            position={props.reverseHandles ? Position.Right : Position.Left}
            style={targetHandleStyle}
          />
        )}
        {!props.disableSource && (
          <Handle
            type="source"
            id="source"
            position={props.reverseHandles ? Position.Left : Position.Right}
            style={sourceHandleStyle}
          />
        )}
        {props.enableStart && (
          <Handle type="source" id="start" position={Position.Right} style={{ ...sourceHandleStyle, top: '85%' }} />
        )}
        {props.enableEnd && (
          <Handle
            type="target"
            id="end"
            position={Position.Left}
            style={{
              ...targetHandleStyle,
              top: '50%', // Same position as main target handle
              opacity: 0, // Invisible
              pointerEvents: 'none', // Non-interactive
            }}
          />
        )}
      </SynPanel>
    </NodeExpandedContext.Provider>
  )
}

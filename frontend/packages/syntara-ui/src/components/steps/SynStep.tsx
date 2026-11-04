import { Icon, Label } from '@patternfly/react-core'
import { RhUiWarningFillIcon } from '@patternfly/react-icons'
import type { NodeProps } from '@xyflow/react'
import React, { useEffect, useMemo, useState } from 'react'

import { ExecutionStatusBadge } from '../../routes/builder/components/ExecutionStatusBadge'
import { useSemanticZoom } from '../../routes/workflows/canvas/nodes/hooks/useSemanticZoom'
import type { StepMenuAction } from '../../routes/workflows/canvas/nodes/hooks/useStepMenuActions'
import { SEMANTIC_ZOOM_TILE_HANDLE_TOP_PX } from '../../routes/workflows/canvas/semanticZoom'
import type { SemanticZoomBranchSource } from '../../routes/workflows/canvas/semanticZoomTypes'
import { STEP_TYPE_COLORS } from '../../routes/workflows/canvas/stepTypeColors'
import type { ActivityStatus } from '../../routes/workflows/execution/types'
import { SynPanel } from '../layout/SynPanel'

import { SynStepConnectionHandles } from './SynStepConnectionHandles'
import { SynStepExpandedAllContext } from './SynStepExpandedAllContext'
import { SynStepExpandedContext } from './SynStepExpandedContext'
import { getSynStepNodeWidth } from './synStepNodeWidth'
import { SynStepSemanticZoomBody } from './SynStepSemanticZoomBody'

type ExecutionState = {
  status: ActivityStatus
  started_at?: string
  completed_at?: string
  error_details?: string
  retry_count?: number
}

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

// eslint-disable-next-line complexity
export function SynStep(props: {
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
  /** When zoomed out, title and type label for the semantic zoom label panel */
  semanticZoomSummary?: { title: string; typeLabel: string }
  /** Step icon shown in the semantic zoom tile (same as the detailed header icon). */
  semanticZoomIcon?: React.ReactNode
  /** Kebab menu actions for semantic zoom (Edit uses the view-details action when present). */
  semanticZoomMenuActions?: readonly StepMenuAction[]
  /** Branch source handles at semantic zoom (no labels; stacked on the tile edge) */
  semanticZoomBranchSources?: readonly SemanticZoomBranchSource[]
  /** Optional stable hook for tests (e.g. canvas node root) */
  rootTestId?: string
}) {
  const { expandAllEvent, collapseAllEvent } = React.use(SynStepExpandedAllContext)
  const expandedContext = useState(true)
  const isCollapsible = props.collapsible ?? true

  const hasSemanticZoomSummary = props.semanticZoomSummary !== undefined
  const isSemanticZoom = useSemanticZoom(hasSemanticZoomSummary)

  const semanticFillColor = props.topBarColor ?? STEP_TYPE_COLORS.generic

  const barRadiusStyle = useMemo(() => {
    const s = props.style
    if (!s) return undefined
    return {
      borderRadius: s.borderRadius,
      borderTopLeftRadius: s.borderTopLeftRadius,
      borderBottomLeftRadius: s.borderBottomLeftRadius,
    }
  }, [props.style])

  const semanticZoomTileStyle = useMemo(() => {
    if (!barRadiusStyle) return undefined
    if (barRadiusStyle.borderTopLeftRadius === '75px') return undefined
    return barRadiusStyle
  }, [barRadiusStyle])

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
  const nodeWidth = getSynStepNodeWidth(isSemanticZoom, props.nodeProps)

  const semanticZoomHandleTop = SEMANTIC_ZOOM_TILE_HANDLE_TOP_PX
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
          background: 'transparent',
          boxShadow: 'none',
          height: 'auto',
          minHeight: 0,
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
    <SynStepExpandedContext.Provider value={expandedContext}>
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
          <SynStepSemanticZoomBody
            title={summary.title}
            typeLabel={summary.typeLabel}
            accentColor={semanticFillColor}
            icon={props.semanticZoomIcon}
            menuActions={props.semanticZoomMenuActions}
            branchSources={props.semanticZoomBranchSources}
            selected={isSelected}
            hasDashedBorder={props.hasDashedBorder ?? false}
            tileStyle={semanticZoomTileStyle}
          />
        ) : (
          props.children
        )}
        {props.showExecutionBadge !== false && props.executionState && (
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
        {hasValidationError && <ValidationErrorBadge />}
        <SynStepConnectionHandles
          isSemanticZoom={isSemanticZoom}
          semanticZoomHandleTop={semanticZoomHandleTop}
          disableTarget={props.disableTarget}
          disableSource={props.disableSource}
          enableStart={props.enableStart}
          enableEnd={props.enableEnd}
          reverseHandles={props.reverseHandles}
        />
      </SynPanel>
    </SynStepExpandedContext.Provider>
  )
}

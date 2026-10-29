import { useNodeId, useStore, useUpdateNodeInternals } from '@xyflow/react'
import { useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'

import { StandardStepHeader } from '../../routes/workflows/canvas/nodes/common/StandardStepHeader'
import { SemanticZoomBranchSourceHandles } from '../../routes/workflows/canvas/nodes/common/SemanticZoomBranchSourceHandles'
import type { StepMenuAction } from '../../routes/workflows/canvas/nodes/hooks/useStepMenuActions'
import { SEMANTIC_ZOOM_TILE_SIZE_PX } from '../../routes/workflows/canvas/semanticZoom'
import type { SemanticZoomBranchSource } from '../../routes/workflows/canvas/semanticZoomTypes'

import { SYN_STEP_DEFAULT_NODE_WIDTH } from './synStepNodeWidth'
import styles from './SynStepSemanticZoomBody.module.css'

function usePreviewInteraction() {
  const rootRef = useRef<HTMLDivElement>(null)
  const [previewOpen, setPreviewOpen] = useState(false)

  const openPreview = () => setPreviewOpen(true)
  const closePreviewIfOutside = (relatedTarget: EventTarget | null) => {
    if (!(relatedTarget instanceof Element) || !rootRef.current?.contains(relatedTarget)) {
      setPreviewOpen(false)
    }
  }

  return { rootRef, previewOpen, openPreview, closePreviewIfOutside }
}

export function SynStepSemanticZoomBody(props: {
  title: string
  typeLabel: string
  accentColor: string
  icon?: ReactNode
  previewIcon?: ReactNode
  menuActions?: readonly StepMenuAction[]
  expandable?: boolean
  branchSources?: readonly SemanticZoomBranchSource[]
  selected: boolean
  hasDashedBorder: boolean
  tileStyle?: Pick<
    CSSProperties,
    | 'borderRadius'
    | 'borderTopLeftRadius'
    | 'borderBottomLeftRadius'
    | 'borderTopRightRadius'
    | 'borderBottomRightRadius'
  >
}): ReactNode {
  const nodeId = useNodeId()
  const updateNodeInternals = useUpdateNodeInternals()
  const viewportZoom = useStore((s) => s.transform[2])
  const previewInverseScale = viewportZoom > 0 ? 1 / viewportZoom : 1
  const { rootRef, previewOpen, openPreview, closePreviewIfOutside } = usePreviewInteraction()
  const previewHeaderIcon = props.previewIcon ?? props.icon

  const menuActions = props.menuActions ?? []

  useLayoutEffect(() => {
    if (!nodeId) return
    updateNodeInternals(nodeId)
  }, [nodeId, updateNodeInternals, props.branchSources?.length])

  const tileRadiusStyle: CSSProperties = {
    borderRadius: props.tileStyle?.borderRadius ?? 'var(--pf-t--global--border--radius--medium)',
    borderTopLeftRadius: props.tileStyle?.borderTopLeftRadius,
    borderBottomLeftRadius: props.tileStyle?.borderBottomLeftRadius,
    borderTopRightRadius: props.tileStyle?.borderTopRightRadius,
    borderBottomRightRadius: props.tileStyle?.borderBottomRightRadius,
  }

  const tileClassName = [
    styles.tile,
    props.hasDashedBorder && !props.selected ? styles.tileDashed : '',
    props.selected ? styles.tileSelected : '',
  ]
    .filter(Boolean)
    .join(' ')

  const ariaLabel = `${props.title}, ${props.typeLabel}`
  const showPreview = previewOpen

  return (
    <div
      ref={rootRef}
      className={styles.root}
      style={
        {
          '--syn-step-semantic-zoom-tile-size': `${SEMANTIC_ZOOM_TILE_SIZE_PX}px`,
          '--syn-step-semantic-zoom-accent': props.accentColor,
          '--syn-step-semantic-zoom-preview-width': `${SYN_STEP_DEFAULT_NODE_WIDTH}px`,
          '--syn-step-semantic-zoom-preview-inverse-scale': `${previewInverseScale}`,
        } as CSSProperties
      }
      data-selected={props.selected ? 'true' : 'false'}
      data-semantic-zoom-preview-open={showPreview ? 'true' : undefined}
      onPointerEnter={openPreview}
      onPointerLeave={(event) => closePreviewIfOutside(event.relatedTarget)}
      onFocusCapture={openPreview}
      onBlurCapture={(event) => {
        const related = event.relatedTarget
        if (related == null) return
        closePreviewIfOutside(related)
      }}
    >
      <div className={styles.tileRegion}>
        <button
          type="button"
          aria-label={ariaLabel}
          className={styles.tileFocusTarget}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              event.stopPropagation()
            }
          }}
        >
          <div className={tileClassName} style={tileRadiusStyle}>
            {props.icon ? <div className={styles.iconSlot}>{props.icon}</div> : null}
          </div>
        </button>

        {showPreview ? (
          <div
            className={`${styles.preview} ${styles.previewOpen} nodrag nopan`}
            data-testid="semantic-zoom-preview"
            onPointerEnter={openPreview}
          >
            <div className={styles.previewCard} style={{ borderTopColor: props.accentColor, ...tileRadiusStyle }}>
              <StandardStepHeader
                icon={previewHeaderIcon}
                title={props.title}
                subtitle={props.typeLabel}
                menuActions={[...menuActions]}
                expandable={props.expandable}
                menuPopperProps={{ position: 'right' }}
              />
            </div>
          </div>
        ) : null}

        <SemanticZoomBranchSourceHandles handles={props.branchSources ?? []} />
      </div>
    </div>
  )
}

import { Flex, FlexItem, Stack, StackItem } from '@patternfly/react-core'
import { useNodeId, useStore, useUpdateNodeInternals } from '@xyflow/react'
import { useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'

import { useIsActiveExecution } from '../../routes/builder/ActiveExecutionContext'
import { useIsExecutionView } from '../../routes/builder/ExecutionViewContext'
import { useIsVersionView } from '../../routes/builder/VersionViewContext'
import { SemanticZoomBranchSourceHandles } from '../../routes/workflows/canvas/nodes/common/SemanticZoomBranchSourceHandles'
import type { StepMenuAction } from '../../routes/workflows/canvas/nodes/hooks/useStepMenuActions'
import { SEMANTIC_ZOOM_TILE_SIZE_PX } from '../../routes/workflows/canvas/semanticZoom'
import type { SemanticZoomBranchSource } from '../../routes/workflows/canvas/semanticZoomTypes'

import { SynStepHeaderActions } from './SynStepHeaderActions'
import { SYN_STEP_DEFAULT_NODE_WIDTH } from './synStepNodeWidth'
import styles from './SynStepSemanticZoomBody.module.css'
import { SynStepTitle } from './SynStepTitle'

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
  /** Header-sized icon for the hover/focus preview (matches full-zoom step header, not the tile). */
  previewIcon?: ReactNode
  menuActions?: readonly StepMenuAction[]
  expandable?: boolean
  /** Invisible source handles on the tile right edge (branching nodes only). */
  branchSources?: readonly SemanticZoomBranchSource[]
  selected: boolean
  hasDashedBorder: boolean
  /** Pass-through from node (e.g. trigger pill radii on the tile). */
  tileStyle?: Pick<CSSProperties, 'borderRadius' | 'borderTopLeftRadius' | 'borderBottomLeftRadius'>
}): ReactNode {
  const nodeId = useNodeId()
  const updateNodeInternals = useUpdateNodeInternals()
  const isExecutionView = useIsExecutionView()
  const isActiveExecution = useIsActiveExecution()
  const nodesConnectable = useStore((s) => s.nodesConnectable)
  const viewportZoom = useStore((s) => s.transform[2])
  const previewInverseScale = viewportZoom > 0 ? 1 / viewportZoom : 1
  const isVersionView = useIsVersionView()
  const { rootRef, previewOpen, openPreview, closePreviewIfOutside } = usePreviewInteraction()
  const previewHeaderIcon = props.previewIcon ?? props.icon

  const menuActions = props.menuActions ?? []
  const showMenuActions =
    menuActions.length > 0 && !isExecutionView && !isActiveExecution && !isVersionView && nodesConnectable

  useLayoutEffect(() => {
    if (!nodeId) return
    updateNodeInternals(nodeId)
  }, [nodeId, updateNodeInternals, props.branchSources?.length])

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
            if (event.key !== 'Enter' && event.key !== ' ') return
            event.stopPropagation()
          }}
        >
          <Flex className={tileClassName} style={props.tileStyle}>
            {props.icon ? <Flex className={styles.iconSlot}>{props.icon}</Flex> : null}
          </Flex>
        </button>

        {showPreview ? (
          <div
            className={`${styles.preview} ${styles.previewOpen} nodrag nopan`}
            data-testid="semantic-zoom-preview"
            onPointerEnter={openPreview}
          >
            <div className={styles.previewCard} style={{ borderTopColor: props.accentColor }}>
              <Stack>
                <StackItem className={styles.previewHeader}>
                  <Flex
                    alignItems={{ default: 'alignItemsFlexStart' }}
                    justifyContent={{ default: 'justifyContentSpaceBetween' }}
                    style={{ gap: 'var(--pf-t--global--spacer--sm)' }}
                  >
                    <Flex
                      alignItems={{ default: 'alignItemsFlexStart' }}
                      style={{ gap: 'var(--pf-t--global--spacer--sm)', minWidth: 0, flex: 1 }}
                    >
                      {previewHeaderIcon ? <FlexItem shrink={{ default: 'shrink' }}>{previewHeaderIcon}</FlexItem> : null}
                      <SynStepTitle title={props.title} subTitle={props.typeLabel} />
                    </Flex>
                    <FlexItem shrink={{ default: 'shrink' }}>
                      <SynStepHeaderActions
                        stepTitle={props.title}
                        menuActions={[...menuActions]}
                        expandable={props.expandable}
                        showMenuActions={showMenuActions}
                        menuPopperProps={{ position: 'right' }}
                      />
                    </FlexItem>
                  </Flex>
                </StackItem>
              </Stack>
            </div>
          </div>
        ) : null}

        <SemanticZoomBranchSourceHandles handles={props.branchSources ?? []} />
      </div>
    </div>
  )
}

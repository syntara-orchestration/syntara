import { Button, Content, ContentVariants, Flex, Icon, Stack, StackItem, Tooltip } from '@patternfly/react-core'
import { RhUiEditIcon } from '@patternfly/react-icons'
import { useNodeId, useStore, useUpdateNodeInternals } from '@xyflow/react'
import { useLayoutEffect, type CSSProperties, type ReactNode } from 'react'

import { useIsActiveExecution } from '../../routes/builder/ActiveExecutionContext'
import { useIsExecutionView } from '../../routes/builder/ExecutionViewContext'
import { useIsVersionView } from '../../routes/builder/VersionViewContext'
import { SemanticZoomBranchSourceHandles } from '../../routes/workflows/canvas/nodes/common/SemanticZoomBranchSourceHandles'
import type { StepMenuAction } from '../../routes/workflows/canvas/nodes/hooks/useStepMenuActions'
import { SEMANTIC_ZOOM_TILE_SIZE_PX } from '../../routes/workflows/canvas/semanticZoom'
import type { SemanticZoomBranchSource } from '../../routes/workflows/canvas/semanticZoomTypes'

import { SynStepMenu } from './SynStepMenu'
import styles from './SynStepSemanticZoomBody.module.css'

export function SynStepSemanticZoomBody(props: {
  title: string
  typeLabel: string
  accentColor: string
  icon?: ReactNode
  menuActions?: readonly StepMenuAction[]
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
  const isVersionView = useIsVersionView()

  const menuActions = props.menuActions ?? []
  const showActions =
    menuActions.length > 0 && !isExecutionView && !isActiveExecution && !isVersionView && nodesConnectable

  const editAction = menuActions.find((action) => action.id === 'view-details')

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

  const tooltipTextColor = 'var(--pf-t--global--text--color--inverse)'
  const tooltipContent = (
    <Stack style={{ textAlign: 'center', color: tooltipTextColor }}>
      <StackItem>
        <Content
          component="p"
          style={{
            margin: 0,
            color: tooltipTextColor,
            fontWeight: 'var(--pf-t--global--font--weight--heading--default)',
          }}
        >
          {props.title}
        </Content>
      </StackItem>
      <StackItem>
        <Content
          component={ContentVariants.small}
          style={{
            margin: 0,
            color: tooltipTextColor,
            opacity: 0.82,
          }}
        >
          {props.typeLabel}
        </Content>
      </StackItem>
    </Stack>
  )

  const ariaLabel = `${props.title}, ${props.typeLabel}`

  return (
    // eslint-disable-next-line syntara/prefer-pf-text-components -- layout shell; children are controls and the icon tile, not text content
    <div
      className={styles.root}
      style={
        {
          '--syn-step-semantic-zoom-tile-size': `${SEMANTIC_ZOOM_TILE_SIZE_PX}px`,
          '--syn-step-semantic-zoom-accent': props.accentColor,
        } as CSSProperties
      }
      data-selected={props.selected ? 'true' : 'false'}
    >
      <div className={styles.tileRegion}>
        <Tooltip content={tooltipContent} position="top">
          <button type="button" aria-label={ariaLabel} className={styles.tooltipTrigger}>
            <Flex className={tileClassName} style={props.tileStyle}>
              {props.icon ? <Flex className={styles.iconSlot}>{props.icon}</Flex> : null}
            </Flex>
          </button>
        </Tooltip>
        {showActions ? (
          <Flex className={`${styles.actions} nodrag nopan`} data-testid="semantic-zoom-actions">
            {editAction ? (
              <Button
                variant="plain"
                aria-label={`Edit ${props.title}`}
                className={`${styles.actionControl} nodrag nopan`}
                onClick={(event) => {
                  event.stopPropagation()
                  editAction.onClick()
                }}
                onMouseDown={(event) => event.stopPropagation()}
              >
                <Icon size="xl">
                  <RhUiEditIcon />
                </Icon>
              </Button>
            ) : null}
            <SynStepMenu
              menuActions={[...menuActions]}
              className={styles.actionControl}
              popperProps={{ position: 'right' }}
            />
          </Flex>
        ) : null}
        <SemanticZoomBranchSourceHandles handles={props.branchSources ?? []} />
      </div>
    </div>
  )
}

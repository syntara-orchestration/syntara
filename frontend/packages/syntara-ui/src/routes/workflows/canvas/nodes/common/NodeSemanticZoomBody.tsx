import { Content, ContentVariants, Stack, StackItem, Tooltip } from '@patternfly/react-core'
import type { CSSProperties, ReactNode } from 'react'

import { SEMANTIC_ZOOM_BAR_HEIGHT_PX } from '../../semanticZoom'
import type { SemanticZoomBranchSource } from '../../semanticZoomTypes'

import styles from './NodeSemanticZoomBody.module.css'
import { SemanticZoomBranchSourceHandles } from './SemanticZoomBranchSourceHandles'

export function NodeSemanticZoomBody(props: {
  title: string
  typeLabel: string
  backgroundColor: string
  /** Invisible source handles on the bar right edge (branching nodes only). */
  branchSources?: readonly SemanticZoomBranchSource[]
  selected: boolean
  hasDashedBorder: boolean
  /** Pass-through from node (e.g. trigger pill radii on the color bar). */
  barStyle?: Pick<CSSProperties, 'borderRadius' | 'borderTopLeftRadius' | 'borderBottomLeftRadius'>
}): ReactNode {
  /** Tooltip surface uses inverse background; Content’s default text color is for the main page and reads as white here. */
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

  const baseBarStyle: CSSProperties = {
    width: '100%',
    height: '100%',
    minHeight: '100%',
    backgroundColor: props.backgroundColor,
    boxSizing: 'border-box',
    ...props.barStyle,
  }

  if (props.hasDashedBorder && !props.selected) {
    baseBarStyle.border = '2px dashed rgba(196, 181, 253, 0.5)'
  } else if (props.selected) {
    baseBarStyle.outline = '2px solid var(--pf-t--global--color--brand--default)'
    baseBarStyle.outlineOffset = 2
  }

  const rowStyle: CSSProperties = {
    position: 'relative',
    width: '100%',
    height: SEMANTIC_ZOOM_BAR_HEIGHT_PX,
    minHeight: SEMANTIC_ZOOM_BAR_HEIGHT_PX,
    // Click bubbles to the ReactFlow node, which selects / opens the builder detail path.
    cursor: 'pointer',
  }

  return (
    <div style={rowStyle}>
      <Tooltip content={tooltipContent} position="top">
        {/*
          PatternFly Tooltip opens on focus; the native <button> gives keyboard
          users a focus target and announces the node name + type to screen readers.
        */}
        <button type="button" aria-label={`${props.title}, ${props.typeLabel}`} className={styles.tooltipTrigger}>
          <div style={baseBarStyle} />
        </button>
      </Tooltip>
      <SemanticZoomBranchSourceHandles handles={props.branchSources ?? []} />
    </div>
  )
}

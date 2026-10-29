import { StackItem } from '@patternfly/react-core'
import { use, type ReactNode } from 'react'

import { SynStepExpandedContext } from './SynStepExpandedContext'
import bodyStyles from './SynStepBody.module.css'

export type SynStepBodyProps = {
  children: ReactNode
  className?: string
}

/**
 * Collapsible, scrollable content area for workflow steps (React Flow node bodies).
 *
 * Features:
 * - Expands/collapses based on SynStepExpandedContext
 * - Uses PatternFly Stack/StackItem components for layout
 */
export function SynStepBody(props: Readonly<SynStepBodyProps>) {
  const expandedState = use(SynStepExpandedContext)
  const expanded = expandedState === null ? true : expandedState[0]

  if (!expanded) {
    return null
  }

  return (
    <StackItem
      data-testid="node-body"
      className="nodrag nopan"
      style={{
        cursor: 'default', // Override node's draggable cursor - this area is scrollable, not draggable
      }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      {/* Content container */}
      <div
        data-testid="node-body-scroll-container"
        className={`nodrag nopan ${bodyStyles.detailsRegion} ${props.className ?? ''}`}
        style={{
          paddingTop: 'var(--pf-t--global--spacer--sm)',
          paddingBottom: 'var(--pf-t--global--spacer--sm)',
          paddingLeft: 'var(--pf-t--global--spacer--md)',
          paddingRight: 'var(--pf-t--global--spacer--md)',
        }}
      >
        {props.children}
      </div>
    </StackItem>
  )
}

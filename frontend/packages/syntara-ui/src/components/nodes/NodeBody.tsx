import { StackItem } from '@patternfly/react-core'
import { use, type ReactNode } from 'react'

import { NodeExpandedContext } from './NodeExpandedContext'

export type NodeBodyProps = {
  children: ReactNode
  className?: string
}

/**
 * Collapsible, scrollable content area for workflow steps (React Flow node bodies).
 *
 * Features:
 * - Expands/collapses based on NodeExpandedContext
 * - Uses PatternFly Stack/StackItem components for layout
 */
export function NodeBody(props: Readonly<NodeBodyProps>) {
  const expandedState = use(NodeExpandedContext)
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
        className={`nodrag nopan ${props.className ?? ''}`}
        style={{
          paddingLeft: 'var(--pf-t--global--spacer--md)',
          paddingRight: 'var(--pf-t--global--spacer--md)',
          paddingBottom: 'var(--pf-t--global--spacer--md)',
        }}
      >
        {props.children}
      </div>
    </StackItem>
  )
}

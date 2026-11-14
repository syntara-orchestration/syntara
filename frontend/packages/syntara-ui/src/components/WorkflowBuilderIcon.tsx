import { RhUiNetworkIcon } from '@patternfly/react-icons'
import type { CSSProperties } from 'react'

type WorkflowBuilderIconProps = Readonly<{
  className?: string
  style?: CSSProperties
}>

/** Workflow trigger glyph shown rotated per the builder prototype. */
export function WorkflowBuilderIcon({ className, style }: WorkflowBuilderIconProps) {
  return (
    <RhUiNetworkIcon
      aria-hidden="true"
      className={className}
      data-testid="workflow-builder-icon"
      style={{ ...style, transform: 'rotate(270deg)' }}
    />
  )
}

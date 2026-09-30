import { Icon } from '@patternfly/react-core'
import { RhUiCaretDownIcon } from '@patternfly/react-icons'
import { use } from 'react'

import { NodeExpandedContext } from './NodeExpandedContext'

export function NodeExpandToggle({ nodeLabel }: Readonly<{ nodeLabel?: string }>) {
  const expandedState = use(NodeExpandedContext)
  const expanded = expandedState === null ? true : expandedState[0]
  const setExpanded = expandedState ? expandedState[1] : () => {}
  if (!expandedState) return null

  const handleToggle = (event: React.SyntheticEvent) => {
    event.stopPropagation()
    setExpanded((expanded) => !expanded)
  }

  const action = expanded ? 'Collapse' : 'Expand'
  const ariaLabel = nodeLabel ? `${action} details for ${nodeLabel}` : `${action} step details`

  return (
    <Icon
      data-testid="node-expand-toggle"
      onClick={handleToggle}
      onMouseDown={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          e.stopPropagation()
          setExpanded((expanded) => !expanded)
        }
      }}
      className="nodrag nopan"
      role="button"
      tabIndex={0}
      aria-label={ariaLabel}
      style={{
        transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
        transition: 'transform 0.2s ease-out',
        cursor: 'pointer',
      }}
    >
      <RhUiCaretDownIcon />
    </Icon>
  )
}

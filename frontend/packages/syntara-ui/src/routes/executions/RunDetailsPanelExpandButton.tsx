import { Button, Tooltip } from '@patternfly/react-core'
import { RhUiCompressArrowsIcon, RhUiExpandArrowsIcon } from '@patternfly/react-icons'

export type RunDetailsPanelExpandControl = {
  isExpanded: boolean
  onToggle: () => void
}

export function RunDetailsPanelExpandButton({ isExpanded, onToggle }: Readonly<RunDetailsPanelExpandControl>) {
  const tooltip = isExpanded ? 'Collapse panel' : 'Expand panel'
  const ariaLabel = isExpanded ? 'Collapse panel' : 'Expand panel'

  return (
    <Tooltip content={tooltip}>
      <Button
        variant="plain"
        aria-label={ariaLabel}
        aria-pressed={isExpanded}
        onClick={onToggle}
        icon={isExpanded ? <RhUiCompressArrowsIcon /> : <RhUiExpandArrowsIcon />}
      />
    </Tooltip>
  )
}

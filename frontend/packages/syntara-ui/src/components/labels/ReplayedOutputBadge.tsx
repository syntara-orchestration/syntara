import { RhUiHistoryIcon } from '@patternfly/react-icons'

import { SynLabel } from './SynLabel'

/**
 * Marks a step that reused a previous run's output instead of executing in this
 * run. Shown only on retried executions, where replayed steps carry the source
 * run's timestamps.
 */
export function ReplayedOutputBadge() {
  return (
    <SynLabel variant="outline" icon={<RhUiHistoryIcon />} data-testid="replayed-output-badge">
      Reused output
    </SynLabel>
  )
}

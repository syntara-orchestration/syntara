import { RhUiWarningFillIcon } from '@patternfly/react-icons'

import { SynLabel } from './SynLabel'

/**
 * Badge indicating an execution has been delayed (first stall detected).
 * Shown when execution.first_stall_detected_at is set.
 */
export function ExecutionDelayedBadge() {
  return (
    <SynLabel variant="outline" status="warning" icon={<RhUiWarningFillIcon />}>
      Delayed
    </SynLabel>
  )
}

import { Button, EmptyState, EmptyStateActions, EmptyStateBody, EmptyStateFooter } from '@patternfly/react-core'
import { RhUiDesktopIcon } from '@patternfly/react-icons'

import { REACT_FLOW_VIEWPORT_EMPTY_STATE } from '../../constants/viewport'

export type SynEmptyStateViewportTooSmallProps = {
  onReturn: () => void
}

/** Full-height empty state when the viewport width is below the minimum for React Flow canvases (1024px). Height is not gated. */
export function SynEmptyStateViewportTooSmall({ onReturn }: Readonly<SynEmptyStateViewportTooSmallProps>) {
  return (
    <EmptyState headingLevel="h2" titleText={REACT_FLOW_VIEWPORT_EMPTY_STATE.title} icon={RhUiDesktopIcon} isFullHeight>
      <EmptyStateBody>{REACT_FLOW_VIEWPORT_EMPTY_STATE.body}</EmptyStateBody>
      <EmptyStateFooter>
        <EmptyStateActions>
          <Button variant="primary" onClick={onReturn}>
            {REACT_FLOW_VIEWPORT_EMPTY_STATE.returnLabel}
          </Button>
        </EmptyStateActions>
      </EmptyStateFooter>
    </EmptyState>
  )
}

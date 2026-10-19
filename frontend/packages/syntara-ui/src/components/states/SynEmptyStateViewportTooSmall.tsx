import { EmptyState, EmptyStateActions, EmptyStateBody, EmptyStateFooter } from '@patternfly/react-core'
import { RhUiDesktopIcon } from '@patternfly/react-icons'

import { REACT_FLOW_VIEWPORT_EMPTY_STATE } from '../../constants/viewport'
import { SynLink } from '../SynLink'

export type SynEmptyStateViewportTooSmallProps = {
  returnTo: string
}

/** Full-height empty state when the viewport width is below the minimum for React Flow canvases (1024px). Height is not gated. */
export function SynEmptyStateViewportTooSmall({ returnTo }: Readonly<SynEmptyStateViewportTooSmallProps>) {
  return (
    <EmptyState headingLevel="h2" titleText={REACT_FLOW_VIEWPORT_EMPTY_STATE.title} icon={RhUiDesktopIcon} isFullHeight>
      <EmptyStateBody>{REACT_FLOW_VIEWPORT_EMPTY_STATE.body}</EmptyStateBody>
      <EmptyStateFooter>
        <EmptyStateActions>
          <SynLink to={returnTo} variant="primary">
            {REACT_FLOW_VIEWPORT_EMPTY_STATE.returnLabel}
          </SynLink>
        </EmptyStateActions>
      </EmptyStateFooter>
    </EmptyState>
  )
}

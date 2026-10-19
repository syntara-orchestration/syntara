import { Button, EmptyState, EmptyStateActions, EmptyStateBody, EmptyStateFooter } from '@patternfly/react-core'
import { RhUiArrowLeftIcon, RhUiSearchIcon, RhUiSyncIcon } from '@patternfly/react-icons'

import { SynLink } from '../../../components/SynLink'

type UserNotFoundStateProps = {
  backTo: string
  onRetry: () => void
  backLabel?: string
}

export function UserNotFoundState({ backTo, onRetry, backLabel = 'Back to users' }: Readonly<UserNotFoundStateProps>) {
  return (
    <EmptyState headingLevel="h2" titleText="User not found" icon={RhUiSearchIcon} isFullHeight>
      <EmptyStateBody>The user you are looking for does not exist or may have been deleted.</EmptyStateBody>
      <EmptyStateFooter>
        <EmptyStateActions>
          <SynLink to={backTo} variant="primary" icon={<RhUiArrowLeftIcon />}>
            {backLabel}
          </SynLink>
          <Button variant="link" icon={<RhUiSyncIcon />} onClick={onRetry}>
            Retry
          </Button>
        </EmptyStateActions>
      </EmptyStateFooter>
    </EmptyState>
  )
}

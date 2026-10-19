import { Button, EmptyState, EmptyStateActions, EmptyStateBody, EmptyStateFooter } from '@patternfly/react-core'
import { RhUiArrowLeftIcon, RhUiSearchIcon, RhUiSyncIcon } from '@patternfly/react-icons'

import { SynLink } from '../../../components/SynLink'

type GroupNotFoundStateProps = {
  backTo: string
  onRetry: () => void
}

export function GroupNotFoundState({ backTo, onRetry }: Readonly<GroupNotFoundStateProps>) {
  return (
    <EmptyState headingLevel="h2" titleText="Group not found" icon={RhUiSearchIcon} isFullHeight>
      <EmptyStateBody>The group you are looking for does not exist or may have been deleted.</EmptyStateBody>
      <EmptyStateFooter>
        <EmptyStateActions>
          <SynLink to={backTo} variant="primary" icon={<RhUiArrowLeftIcon />}>
            Back to groups
          </SynLink>
          <Button variant="link" icon={<RhUiSyncIcon />} onClick={onRetry}>
            Retry
          </Button>
        </EmptyStateActions>
      </EmptyStateFooter>
    </EmptyState>
  )
}

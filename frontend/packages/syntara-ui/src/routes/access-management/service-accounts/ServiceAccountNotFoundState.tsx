import { Button, EmptyState, EmptyStateActions, EmptyStateBody, EmptyStateFooter } from '@patternfly/react-core'
import { RhUiArrowLeftIcon, RhUiErrorFillIcon, RhUiSyncIcon } from '@patternfly/react-icons'

import { SynLink } from '../../../components/SynLink'

type ServiceAccountNotFoundStateProps = {
  backTo: string
  onRetry: () => void
}

export function ServiceAccountNotFoundState({ backTo, onRetry }: Readonly<ServiceAccountNotFoundStateProps>) {
  return (
    <EmptyState headingLevel="h2" titleText="Service account not found" icon={RhUiErrorFillIcon} isFullHeight>
      <EmptyStateBody>The service account you are looking for does not exist or may have been deleted.</EmptyStateBody>
      <EmptyStateFooter>
        <EmptyStateActions>
          <SynLink to={backTo} variant="primary" icon={<RhUiArrowLeftIcon />}>
            Back to service accounts
          </SynLink>
          <Button variant="link" icon={<RhUiSyncIcon />} onClick={onRetry}>
            Retry
          </Button>
        </EmptyStateActions>
      </EmptyStateFooter>
    </EmptyState>
  )
}

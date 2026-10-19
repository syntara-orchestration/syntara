import { Button, EmptyState, EmptyStateActions, EmptyStateBody, EmptyStateFooter } from '@patternfly/react-core'
import { RhUiArrowLeftIcon, RhUiSearchIcon, RhUiSyncIcon } from '@patternfly/react-icons'

import { SynLink } from '../../../components/SynLink'

type ProjectNotFoundStateProps = {
  backTo: string
  onRetry: () => void
}

export function ProjectNotFoundState({ backTo, onRetry }: Readonly<ProjectNotFoundStateProps>) {
  return (
    <EmptyState headingLevel="h2" titleText="Project not found" icon={RhUiSearchIcon} isFullHeight>
      <EmptyStateBody>The project you are looking for does not exist or may have been deleted.</EmptyStateBody>
      <EmptyStateFooter>
        <EmptyStateActions>
          <SynLink to={backTo} variant="primary" icon={<RhUiArrowLeftIcon />}>
            Back to projects
          </SynLink>
          <Button variant="link" icon={<RhUiSyncIcon />} onClick={onRetry}>
            Retry
          </Button>
        </EmptyStateActions>
      </EmptyStateFooter>
    </EmptyState>
  )
}

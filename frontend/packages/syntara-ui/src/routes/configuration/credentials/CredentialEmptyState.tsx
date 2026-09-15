import { Button, EmptyState, EmptyStateActions, EmptyStateBody, EmptyStateFooter } from '@patternfly/react-core'
import { PlusCircleIcon } from '@patternfly/react-icons'

type CredentialEmptyStateProps = {
  onCreateCredential?: () => void
}

export function CredentialEmptyState({ onCreateCredential }: Readonly<CredentialEmptyStateProps>) {
  return (
    <EmptyState headingLevel="h2" icon={PlusCircleIcon} titleText="No credentials yet">
      <EmptyStateBody>
        Credentials provide secure authentication for workflows, integrations, and AI agents. Create your first
        credential to get started.
      </EmptyStateBody>
      {onCreateCredential && (
        <EmptyStateFooter>
          <EmptyStateActions>
            <Button variant="primary" onClick={onCreateCredential}>
              Create credential
            </Button>
          </EmptyStateActions>
        </EmptyStateFooter>
      )}
    </EmptyState>
  )
}

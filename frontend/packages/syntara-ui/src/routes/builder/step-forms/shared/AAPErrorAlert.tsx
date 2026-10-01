import { Alert, Button, StackItem } from '@patternfly/react-core'

import { getErrorMessage, isRetryableError } from '../../../../utils/apiErrors'

type AAPErrorAlertProps = {
  readonly error: Error | null
  readonly onRetry: () => void
}

/**
 * Shared error alert for AAP resource loading failures.
 * Shows retry button for retryable errors (network, timeout, etc.).
 */
export function AAPErrorAlert({ error, onRetry }: AAPErrorAlertProps) {
  if (!error) return null

  return (
    <StackItem>
      <Alert
        variant="danger"
        title="Failed to load AAP resources"
        isInline
        actionLinks={
          isRetryableError(error) ? (
            <Button variant="link" onClick={onRetry}>
              Retry
            </Button>
          ) : undefined
        }
      >
        {getErrorMessage(error)}
      </Alert>
    </StackItem>
  )
}

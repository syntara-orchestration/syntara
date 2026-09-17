import { Button, EmptyState, EmptyStateActions, EmptyStateBody, EmptyStateFooter } from '@patternfly/react-core'
import { RhUiErrorFillIcon } from '@patternfly/react-icons'

import { getErrorMessage, getErrorTitle, isRetryableError, isServiceUnavailableError } from '../../utils/apiErrors'

import { SynEmptyStateServiceUnavailable } from './SynEmptyStateServiceUnavailable'

/** Props for {@link SynErrorState}. */
export type SynErrorStateProps = {
  title?: string
  message: unknown
  onRetry?: () => void
}

/**
 * Full-height empty state for API or query errors.
 *
 * Derives the title and message from the error automatically; pass `title` to override.
 * Shows a Retry button only when the error is retryable and `onRetry` is provided.
 * 503 Service Unavailable errors render {@link SynEmptyStateServiceUnavailable} instead.
 */
export function SynErrorState(props: SynErrorStateProps) {
  const { title, message, onRetry } = props

  if (isServiceUnavailableError(message)) {
    return <SynEmptyStateServiceUnavailable description={getErrorMessage(message)} />
  }

  const errorTitle = title ?? getErrorTitle(message)
  const errorMessage = getErrorMessage(message)
  const retryable = isRetryableError(message)

  return (
    <EmptyState
      data-testid="error-state"
      headingLevel="h2"
      titleText={errorTitle}
      icon={RhUiErrorFillIcon}
      isFullHeight
    >
      <EmptyStateBody>{errorMessage}</EmptyStateBody>
      {retryable && onRetry && (
        <EmptyStateFooter>
          <EmptyStateActions>
            <Button variant="primary" onClick={onRetry}>
              Retry
            </Button>
          </EmptyStateActions>
        </EmptyStateFooter>
      )}
    </EmptyState>
  )
}

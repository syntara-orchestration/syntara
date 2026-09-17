import { useApiErrorAlert } from '../../hooks/useApiErrorAlert'
import { getErrorMessage, isServiceUnavailableError } from '../../utils/apiErrors'

import { SynEmptyStateServiceUnavailable } from './SynEmptyStateServiceUnavailable'
import { SynErrorState } from './SynErrorState'
import { SynLoadingState } from './SynLoadingState'

export type QueryStateOptions = {
  title?: string
  onRetry?: () => void
}

/**
 * Hook to handle query state rendering for loading, error, and 503 states.
 *
 * Automatically detects 503 Service Unavailable errors and renders
 * the appropriate component with the error message from the API.
 *
 * @param state - Query state object with error, isPending, and optional refetch properties
 * @param titleOrOptions - Optional title string or options object with title and onRetry callback
 * @returns JSX element for the current state, or null if data is ready
 *
 * @example
 * // Basic usage
 * const query = workflowClient.useQuery('get', '/workflows')
 * const queryState = useQueryState(query, 'Error loading workflows')
 *
 * @example
 * // With retry support
 * const query = workflowClient.useQuery('get', '/workflows')
 * const queryState = useQueryState(query, {
 *   title: 'Error loading workflows',
 *   onRetry: () => query.refetch()
 * })
 *
 * if (queryState) return queryState // Renders loading, error, or 503 state
 *
 * // Render successful data...
 * return <WorkflowList data={query.data} />
 */
export function useQueryState(
  state: { error: unknown; isPending: boolean; refetch?: () => void },
  titleOrOptions?: string | QueryStateOptions
) {
  const { error, isPending, refetch } = state

  // Support both old API (string) and new API (options object)
  const options = typeof titleOrOptions === 'string' ? { title: titleOrOptions } : (titleOrOptions ?? {})
  const { title, onRetry } = options

  // Show an alert for query errors (deduped). Suppress 503 here since we render a 503-specific EmptyState.
  useApiErrorAlert(error, { title, suppress503: true })

  if (error) {
    // Check for 503 Service Unavailable errors
    if (isServiceUnavailableError(error)) {
      return <SynEmptyStateServiceUnavailable description={getErrorMessage(error)} />
    }

    // Regular errors - pass retry handler (prefer explicit onRetry, fallback to refetch)
    return <SynErrorState title={title} message={error} onRetry={onRetry ?? refetch} />
  }

  if (isPending) {
    return <SynLoadingState />
  }

  return null
}

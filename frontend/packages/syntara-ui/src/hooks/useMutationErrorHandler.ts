import { useCallback } from 'react'

import { useAlerts } from '../providers/alerts'
import {
  getErrorMessage,
  getErrorTitle,
  isRetryableError,
  isServiceUnavailableError,
  isValidationError,
} from '../utils/apiErrors'

export type MutationErrorHandlerOptions = {
  /** Title for the error alert */
  title?: string
  /** Additional context to include in the error message */
  context?: string
  /** Custom handler for 503 Service Unavailable errors */
  on503?: () => void
  /** Custom handler for retryable errors */
  onRetryable?: () => void
  /**
   * If true, the alert will NOT auto-dismiss (user must dismiss it).
   * If omitted, validation errors (typically 422 / FastAPI detail arrays) default to persistent.
   */
  persist?: boolean
}

/**
 * Hook for consistent error handling in mutations with special 503 support.
 *
 * Features:
 * - Automatic 503 detection with warning alert (not error)
 * - Consistent error message extraction from various formats
 * - Custom 503 handler support for component-specific behavior
 * - Integration with useAlerts from components/alerts
 *
 * @returns A function that creates an error handler for mutation onError callbacks
 *
 * @example
 * // Basic usage
 * const handleError = useMutationErrorHandler()
 * const { mutate } = workflowClient.useMutation('post', '/workflows')
 * mutate(data, {
 *   onError: handleError({ title: 'Failed to create workflow' })
 * })
 *
 * @example
 * // With custom 503 handling
 * const [showServiceUnavailable, setShowServiceUnavailable] = useState(false)
 * mutate(data, {
 *   onError: handleError({
 *     title: 'Request failed',
 *     on503: () => setShowServiceUnavailable(true)
 *   })
 * })
 *
 * @example
 * // With context for better error messages
 * mutate(data, {
 *   onError: handleError({
 *     title: 'Workflow failed',
 *     context: `Workflow "${workflow.name}"`
 *   })
 * })
 */
export function useMutationErrorHandler() {
  const { showAlert } = useAlerts()

  return useCallback(
    (options: MutationErrorHandlerOptions = {}) => {
      const { title, context, on503, onRetryable, persist } = options

      return (error: unknown) => {
        const errorMessage = getErrorMessage(error)
        const errorTitle = title || getErrorTitle(error)

        // Build full message with context if provided
        const fullMessage = context ? `${context}: ${errorMessage}` : errorMessage

        // Default: keep validation errors visible until user dismisses them.
        const autoDismiss = !(persist ?? isValidationError(error))

        // Check if error is retryable
        const retryable = isRetryableError(error)

        if (isServiceUnavailableError(error)) {
          // 503 errors get a warning (amber) instead of error (red)
          // because they're typically configuration issues, not user errors
          showAlert({ variant: 'warning', title: errorTitle, description: fullMessage, autoDismiss })

          // Call custom 503 handler if provided
          if (on503) {
            on503()
          }
        } else {
          // Regular errors (map 'error' to 'danger' for PatternFly)
          showAlert({ variant: 'danger', title: errorTitle, description: fullMessage, autoDismiss })
        }

        // Call retryable handler if provided
        if (retryable && onRetryable) {
          onRetryable()
        }
      }
    },
    [showAlert]
  )
}

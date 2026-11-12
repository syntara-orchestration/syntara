import { useEffect, useRef } from 'react'

import { useAlerts } from '../providers/alerts'
import {
  getErrorMessage,
  getErrorStatus,
  getErrorTitle,
  isForbiddenError,
  isServiceUnavailableError,
} from '../utils/apiErrors'

export type UseApiErrorAlertOptions = {
  /** Override the alert title (defaults to parsed title or "Error") */
  title?: string
  /** Override the parsed backend message with user-facing copy */
  message?: string
  /** Additional context prefixed to the parsed error message */
  context?: string
  /** If true, do not show an alert for 503 errors (useful when rendering a 503 EmptyState) */
  suppress503?: boolean
}

/**
 * Shows a deduped alert for an API error, using parsed 4xx/5xx response messages by default.
 *
 * Pass a message override when the UI should show application-specific copy instead.
 *
 * 403 Forbidden errors are silently suppressed: they indicate "access denied",
 * which is handled by page-level empty/denied states — a redundant toast adds
 * no value and can flash before the denied UI mounts.
 */
export function useApiErrorAlert(error: unknown, options: UseApiErrorAlertOptions = {}) {
  const { showError, showWarning } = useAlerts()
  const lastKeyRef = useRef<string | null>(null)

  const title = options.title
  const messageOverride = options.message
  const context = options.context
  const suppress503 = options.suppress503

  useEffect(() => {
    if (!error) {
      lastKeyRef.current = null
      return
    }

    const message = messageOverride ?? getErrorMessage(error)
    const status = getErrorStatus(error)
    const errorTitle = title ?? getErrorTitle(error)
    const fullMessage = context ? `${context}: ${message}` : message
    const key = `${status ?? ''}::${errorTitle}::${fullMessage}`

    if (lastKeyRef.current === key) {
      return
    }
    lastKeyRef.current = key

    if (isForbiddenError(error)) return

    if (isServiceUnavailableError(error)) {
      if (!suppress503) {
        showWarning({ title: errorTitle, description: fullMessage })
      }
      return
    }

    showError({ title: errorTitle, description: fullMessage })
  }, [error, title, messageOverride, context, suppress503, showError, showWarning])
}

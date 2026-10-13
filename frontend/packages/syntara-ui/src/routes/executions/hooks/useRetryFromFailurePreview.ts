import { executionsClient } from '../../../client'

type UseRetryFromFailurePreviewParams = {
  executionId: string
  /** The preview is only worth fetching once the operator asks for it. */
  enabled: boolean
}

/**
 * Read-only preview of a retry from failure.
 *
 * Fetches only while the dialog is open. Returns `200` with `eligible: false`
 * and a `reason` when the backend refuses, so a rejection is data rather than
 * an error state — only transport failures surface as `isError`.
 */
export function useRetryFromFailurePreview({ executionId, enabled }: UseRetryFromFailurePreviewParams) {
  /* v8 ignore start -- v8 emits phantom branches from the compiled generic useQuery call */
  const previewQuery = executionsClient.useQuery(
    'get',
    '/executions/{execution_id}/retry-from-failure-preview',
    {
      params: { path: { execution_id: executionId } },
    },
    { enabled, retry: false }
  )
  /* v8 ignore stop */

  return {
    preview: previewQuery.data,
    isLoading: enabled && previewQuery.isPending,
    isError: previewQuery.isError,
  }
}

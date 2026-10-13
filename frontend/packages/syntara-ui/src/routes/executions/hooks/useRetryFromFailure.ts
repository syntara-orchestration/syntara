import { useQueryClient } from '@tanstack/react-query'

import { executionsClient } from '../../../client'
import { useAlerts } from '../../../providers/alerts/AlertContext'
import { getErrorMessage } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'

type UseRetryFromFailureParams = {
  executionId: string
  onSuccess?: (newExecutionId: string) => void
}

function invalidateRetryQueries(queryClient: ReturnType<typeof useQueryClient>) {
  detachPromise(
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ['get', '/executions/{execution_id}'] }),
      queryClient.invalidateQueries({ queryKey: ['get', '/executions/{execution_id}/activities'] }),
      queryClient.invalidateQueries({ queryKey: ['get', '/executions'] }),
    ])
  )
}

/**
 * Retry an execution from its failure points, creating a new execution linked
 * to the source.
 *
 * The backend repeats the full validation chain, so a retry that raced a state
 * change rejects here rather than silently starting a full re-run. Pass
 * `retryPointIds` to resume from a subset; omitting it selects every currently
 * failed node.
 */
export function useRetryFromFailure({ executionId, onSuccess }: UseRetryFromFailureParams) {
  const { showSuccess, showError } = useAlerts()
  const queryClient = useQueryClient()
  /* v8 ignore start -- v8 emits phantom branches from the compiled generic useMutation call */
  const retryMutation = executionsClient.useMutation('post', '/executions/{execution_id}/retry-from-failure')
  /* v8 ignore stop */

  function handleRetry(retryPointIds?: string[]) {
    retryMutation.mutate(
      {
        params: { path: { execution_id: executionId } },
        body: retryPointIds?.length ? { retry_point_ids: retryPointIds } : {},
      },
      {
        onSuccess(data) {
          showSuccess({ title: 'Retry started' })
          invalidateRetryQueries(queryClient)
          if (data?.id) {
            onSuccess?.(data.id)
          }
        },
        onError(error: unknown) {
          showError({ title: 'Failed to retry from failure', description: getErrorMessage(error) })
        },
      }
    )
    /* v8 ignore start -- v8 phantom branches on handleRetry closing brace and return */
  }

  return { handleRetry, isPending: retryMutation.isPending }
  /* v8 ignore stop */
}
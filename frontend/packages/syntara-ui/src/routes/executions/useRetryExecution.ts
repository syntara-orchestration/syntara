import { useQueryClient } from '@tanstack/react-query'

import { executionsClient } from '../../client'
import { useAlerts } from '../../providers/alerts/AlertContext'
import { formatWorkflowLaunchRejection, getErrorMessage } from '../../utils/apiErrors'
import { detachPromise } from '../../utils/detachPromise'

function invalidateExecutionQueries(queryClient: ReturnType<typeof useQueryClient>) {
  detachPromise(
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ['get', '/executions/{execution_id}'] }),
      queryClient.invalidateQueries({ queryKey: ['get', '/executions/{execution_id}/activities'] }),
      queryClient.invalidateQueries({ queryKey: ['get', '/executions'] }),
    ])
  )
}

export function useRetryExecution(executionId: string, onSuccess?: (newExecutionId: string) => void) {
  const { showSuccess, showError } = useAlerts()
  const queryClient = useQueryClient()
  /* v8 ignore start -- v8 emits phantom branches from the compiled generic useMutation call */
  const retryMutation = executionsClient.useMutation('post', '/executions/{execution_id}/retry')
  /* v8 ignore stop */

  function handleRetry() {
    retryMutation.mutate(
      { params: { path: { execution_id: executionId } } },
      {
        onSuccess(data) {
          showSuccess({ title: 'Execution retry started' })
          invalidateExecutionQueries(queryClient)
          if (data?.id) {
            onSuccess?.(data.id)
          }
        },
        onError(error: unknown) {
          if (formatWorkflowLaunchRejection(error)) invalidateExecutionQueries(queryClient)
          showError({ title: 'Failed to retry execution', description: getErrorMessage(error) })
        },
      }
    )
    /* v8 ignore start -- v8 phantom branches on handleRetry closing brace and return */
  }

  return { handleRetry, isPending: retryMutation.isPending }
  /* v8 ignore stop */
}

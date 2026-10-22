import type { ExecutionsAPI } from '@syntara/contracts'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import { detachPromise } from '../../../utils/detachPromise'
import { resolveRetryReplayBaseline } from '../../builder/utils/replayedNodes'
import { useExecutionWebSocket } from '../../workflows/hooks/useExecutionWebSocket'
import { useExecutionStore } from '../../workflows/stores/useExecutionStore'

type Execution = ExecutionsAPI.components['schemas']['ExecutionRead']
type ActivityData = ExecutionsAPI.components['schemas']['ActivityData']
type ActivityExecution = ExecutionsAPI.components['schemas']['ActivityExecution']

type WorkflowNodeLike = { id: string }

type WorkflowDefinitionLike = {
  triggers?: WorkflowNodeLike[]
  nodes?: WorkflowNodeLike[]
  workflow?: { activities?: WorkflowNodeLike[] }
}

export function useExecutionStreaming(executionId: string | undefined, execution: Execution | undefined) {
  const queryClient = useQueryClient()
  const shouldStream =
    execution?.status === 'running' || execution?.status === 'pending' || execution?.status === 'paused'
  useExecutionWebSocket(executionId ?? '', {
    enabled: shouldStream && !!executionId,
    onExecutionComplete: () => {
      detachPromise(
        Promise.all([
          queryClient.invalidateQueries({
            queryKey: ['get', '/executions/{execution_id}'],
          }),
          queryClient.invalidateQueries({
            queryKey: ['get', '/executions'],
          }),
        ])
      )
    },
  })
}

export function useSyncActivityStore(
  execution: Execution | undefined,
  activities: (ActivityData | ActivityExecution)[]
) {
  const { setActivityExecutions, injectPendingStates, setRetryReplayBaseline } = useExecutionStore.getState()

  // Terminal retried runs never stream, so `visualization` (and the replay
  // baseline it carries) is never populated. Resolve the baseline from REST so
  // replay indicators render on the detail page for completed/failed retries.
  const retriedFrom = execution?.retried_from_execution_id ?? null
  const createdAt = execution?.created_at
  useEffect(() => {
    setRetryReplayBaseline(resolveRetryReplayBaseline(createdAt, retriedFrom))
  }, [createdAt, retriedFrom, setRetryReplayBaseline])

  useEffect(() => {
    if (activities.length > 0) {
      setActivityExecutions(activities)
    } else if (execution?.status === 'pending' || execution?.status === 'running' || execution?.status === 'paused') {
      const { activityStates } = useExecutionStore.getState()
      if (activityStates.size === 0) {
        const wfDef = execution?.workflow_definition as unknown as WorkflowDefinitionLike | undefined
        const triggers = wfDef?.triggers ?? []
        const nodes = wfDef?.nodes ?? wfDef?.workflow?.activities ?? []
        const nodeIds = [...triggers, ...nodes].map((n) => n.id)
        if (nodeIds.length > 0) {
          injectPendingStates(nodeIds)
        }
      }
    } else {
      setActivityExecutions([])
    }
  }, [
    activities,
    execution?.id,
    execution?.status,
    execution?.workflow_definition,
    setActivityExecutions,
    injectPendingStates,
  ])
}

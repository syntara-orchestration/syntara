import type { ExecutionsAPI } from '@syntara/contracts'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import * as routeRefs from '../../../app/routes/routeReferences'
import { detachPromise } from '../../../utils/detachPromise'
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
            queryKey: ['get', routeRefs.executionsListRoute.fullPath],
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
  const { setActivityExecutions, injectPendingStates } = useExecutionStore.getState()
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

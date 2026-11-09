import * as routeRefs from '../../../app/routes/routeReferences'
import { executionsClient, workflowClient } from '../../../client'
import { WORKFLOWS_LIST_PARAMS_FOR_DEFAULT_NAME } from '../utils/workflowListQuery'

export function useBuilderContentQueries(options: {
  workflowId: string | null
  isNew: boolean
  executionsQueryParams: Record<string, unknown>
  mostRecentExecutionId: string | null
  mostRecentRunPanelOpen: boolean
}) {
  const { workflowId, isNew, executionsQueryParams, mostRecentExecutionId, mostRecentRunPanelOpen } = options

  const executionsQuery = executionsClient.useQuery(
    'get',
    routeRefs.executionsListRoute.fullPath,
    {
      params: { query: executionsQueryParams },
    },
    {
      enabled: !!workflowId && !isNew,
      staleTime: 30000,
      gcTime: 300000,
    }
  )

  const mostRecentExecutionQuery = executionsClient.useQuery(
    'get',
    '/executions/{execution_id}',
    {
      params: {
        path: { execution_id: mostRecentExecutionId ?? '' },
        query: { include: 'activities' },
      },
    },
    { enabled: !!mostRecentExecutionId && mostRecentRunPanelOpen }
  )

  const workflowsListQuery = workflowClient.useQuery('get', '/workflows', WORKFLOWS_LIST_PARAMS_FOR_DEFAULT_NAME, {
    enabled: isNew,
  })

  return { executionsQuery, mostRecentExecutionQuery, workflowsListQuery }
}

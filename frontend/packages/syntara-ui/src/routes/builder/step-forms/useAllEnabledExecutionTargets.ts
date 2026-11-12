import type { ExecutionPlaneAPI } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'

import { executionPlaneFetchClient } from '../../../client'
import { fetchAllPages, MAX_PAGE_SIZE } from '../../../utils/fetchAllPages'

export type ExecutionTargetRead = ExecutionPlaneAPI.components['schemas']['ExecutionTargetRead']

async function fetchAllEnabledExecutionTargets(): Promise<ExecutionTargetRead[]> {
  return fetchAllPages<ExecutionTargetRead>((cursor) =>
    executionPlaneFetchClient.GET('/api/execution_plane/v1/execution_targets', {
      params: {
        query: {
          sort: 'name',
          enabled: 'true',
          limit: MAX_PAGE_SIZE,
          cursor,
        },
      },
    })
  )
}

export function useAllEnabledExecutionTargets() {
  const {
    data: targets = [],
    isPending,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['all-enabled-execution-targets'],
    queryFn: fetchAllEnabledExecutionTargets,
  })

  return { targets, isLoading: isPending, isError, error, refetch }
}

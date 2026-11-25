import { executionPlaneClient } from '../../client'

type ExecutionTargetUsage = {
  activeWorkloadCount: number
  isLoadingUsage: boolean
  usageFetchError: boolean
}

/**
 * Fetches active workload usage for an execution target while a confirmation dialog is open.
 */
export function useExecutionTargetUsage(targetId: string | null): ExecutionTargetUsage {
  const usageQuery = executionPlaneClient.useQuery(
    'get',
    '/api/execution_plane/v1/execution_targets/{target_id}/usage',
    { params: { path: { target_id: targetId ?? '' } } },
    { enabled: !!targetId }
  )

  return {
    activeWorkloadCount: usageQuery.data?.active_workload_count ?? 0,
    isLoadingUsage: usageQuery.isLoading && !!targetId,
    usageFetchError: !!usageQuery.error,
  }
}

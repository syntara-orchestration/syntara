import type { WorkflowAPI } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'

import { workflowFetchClient } from '../../client'
import { fetchAllPages, MAX_PAGE_SIZE } from '../../utils/fetchAllPages'

type WorkflowRead = WorkflowAPI.components['schemas']['WorkflowRead']

async function fetchAllWorkflows(): Promise<WorkflowRead[]> {
  return fetchAllPages<WorkflowRead>((cursor) =>
    workflowFetchClient.GET('/workflows', {
      params: { query: { sort: 'name', limit: MAX_PAGE_SIZE, cursor } },
    })
  )
}

type UseAllWorkflowsOptions = {
  /** When false, skips the fetch. Defaults to true. */
  enabled?: boolean
}

/**
 * Full workflow list via cursor pagination. Use for command-palette / dropdown
 * catalogs, not paginated tables.
 */
export function useAllWorkflows(options?: UseAllWorkflowsOptions) {
  const enabled = options?.enabled ?? true
  const {
    data: workflows = [],
    isPending,
    error,
    refetch,
  } = useQuery({
    queryKey: ['all-workflows'],
    queryFn: fetchAllWorkflows,
    enabled,
    staleTime: 60_000,
  })
  return { workflows, isLoading: enabled && isPending, error, refetch }
}

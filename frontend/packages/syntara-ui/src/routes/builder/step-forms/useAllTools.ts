import type { ToolManagerAPI } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'

import { toolManagerFetchClient } from '../../../client'
import { fetchAllPages, MAX_PAGE_SIZE } from '../../../utils/fetchAllPages'

type ToolWithParameters = ToolManagerAPI.components['schemas']['ToolWithParameters']

async function fetchAllTools(): Promise<ToolWithParameters[]> {
  return fetchAllPages<ToolWithParameters>((cursor) =>
    toolManagerFetchClient.GET('/tools', {
      params: { query: { sort: 'name', limit: MAX_PAGE_SIZE, cursor } },
    })
  )
}

export function useAllTools() {
  const {
    data: tools = [],
    isPending,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['all-tools'],
    queryFn: fetchAllTools,
  })
  return { tools, isLoading: isPending, isError, refetch }
}

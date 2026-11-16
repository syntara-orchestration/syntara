import type { Tool, IntegrationsAPI } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'

import { integrationsFetchClient } from '../../../../client'
import { fetchAllPages, MAX_PAGE_SIZE } from '../../../../utils/fetchAllPages'

type ToolWithParameters = IntegrationsAPI.components['schemas']['ToolWithParameters']

function isToolRow(row: ToolWithParameters): row is Tool {
  return typeof row.id === 'string'
}

async function fetchAllIntegrationTools(integrationId: string): Promise<Tool[]> {
  const rows = await fetchAllPages<ToolWithParameters>((cursor) =>
    integrationsFetchClient.GET('/integrations/{integration_id}/tools', {
      params: { path: { integration_id: integrationId }, query: { sort: 'name', limit: MAX_PAGE_SIZE, cursor } },
    })
  )
  return rows.filter(isToolRow)
}

export function useAllIntegrationTools(integrationId: string) {
  const {
    data: tools = [],
    isPending,
    error,
    refetch,
  } = useQuery({
    queryKey: ['all-integration-tools', integrationId],
    queryFn: () => fetchAllIntegrationTools(integrationId),
    enabled: !!integrationId,
  })
  return { tools, isLoading: isPending, error, refetch }
}

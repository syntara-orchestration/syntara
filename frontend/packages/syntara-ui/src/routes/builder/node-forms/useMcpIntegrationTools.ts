import type { IntegrationsAPI } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'

import { integrationsFetchClient } from '../../../client'
import { fetchAllPages, MAX_PAGE_SIZE } from '../../../utils/fetchAllPages'

type ToolWithParameters = IntegrationsAPI.components['schemas']['ToolWithParameters']

async function fetchIntegrationTools(integrationId: string): Promise<ToolWithParameters[]> {
  return fetchAllPages<ToolWithParameters>((cursor) =>
    integrationsFetchClient.GET('/integrations/{integration_id}/tools', {
      params: {
        path: { integration_id: integrationId },
        query: { sort: 'name', limit: MAX_PAGE_SIZE, cursor },
      },
    })
  )
}

/**
 * Tools discovered on a single `mcp_server` integration.
 *
 * Backed by `GET /integrations/{integration_id}/tools` — the same listing the
 * integration detail page uses. Disabled until an integration is selected.
 */
export function useMcpIntegrationTools(integrationId: string | undefined) {
  const {
    data: tools = [],
    isPending,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['mcp-integration-tools', integrationId],
    queryFn: () => fetchIntegrationTools(integrationId ?? ''),
    enabled: Boolean(integrationId),
  })

  return { tools, isLoading: Boolean(integrationId) && isPending, isError, refetch }
}

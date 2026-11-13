import { IntegrationTypeEnum, type IntegrationsAPI } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'

import { integrationsFetchClient } from '../../../client'
import { fetchAllPages, MAX_PAGE_SIZE } from '../../../utils/fetchAllPages'
import { projectIdParam } from '../../../utils/queryParams'

type IntegrationOption =
  | IntegrationsAPI.components['schemas']['IntegrationRead']
  | IntegrationsAPI.components['schemas']['KafkaIntegrationRead']

export function useAllIntegrations(
  integrationType: typeof IntegrationTypeEnum.MCP_SERVER | typeof IntegrationTypeEnum.KAFKA,
  projectId?: string
) {
  // Empty and absent project IDs produce the same request and must share a cache entry.
  const projectScope = projectId || undefined
  return useQuery({
    queryKey: ['builder-integrations', integrationType, projectScope],
    queryFn: () =>
      fetchAllPages<IntegrationOption>((cursor) =>
        integrationsFetchClient.GET(
          integrationType === IntegrationTypeEnum.KAFKA ? '/kafka_integrations' : '/integrations',
          {
            params: {
              query: {
                ...(integrationType === IntegrationTypeEnum.KAFKA
                  ? {}
                  : { integration_type: IntegrationTypeEnum.MCP_SERVER }),
                enabled: true,
                ...projectIdParam(projectScope),
                limit: MAX_PAGE_SIZE,
                cursor,
              },
            },
          }
        )
      ),
  })
}

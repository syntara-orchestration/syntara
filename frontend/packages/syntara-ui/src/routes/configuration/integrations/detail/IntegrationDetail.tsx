import { useParams } from '@tanstack/react-router'

import { integrationsClient } from '../../../../client'
import { SynErrorState } from '../../../../components/states/SynErrorState'
import { useQueryState } from '../../../../components/states/useQueryState'
import { detachPromise } from '../../../../utils/detachPromise'

import { IntegrationDetailContent, IntegrationDetailEarlyShell } from './IntegrationDetailContent'

export function IntegrationDetail() {
  const { integrationId }: { integrationId: string } = useParams({ strict: false })

  const query = integrationsClient.useQuery(
    'get',
    '/integrations/{integration_id}',
    { params: { path: { integration_id: integrationId } } },
    { enabled: integrationId.length > 0 }
  )
  const integration = query.data

  const queryState = useQueryState(query, {
    title: 'Error loading integration',
    onRetry: () => detachPromise(query.refetch()),
  })

  if (!integrationId) {
    return (
      <IntegrationDetailEarlyShell title="Error">
        <SynErrorState title="Invalid integration" message="No integration ID provided" />
      </IntegrationDetailEarlyShell>
    )
  }

  if (queryState) {
    return <IntegrationDetailEarlyShell title="Integration">{queryState}</IntegrationDetailEarlyShell>
  }

  if (!integration?.id) return null

  return <IntegrationDetailContent integration={integration} onRefetch={() => query.refetch()} />
}

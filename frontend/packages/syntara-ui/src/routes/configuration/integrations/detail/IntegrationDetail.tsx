import { useParams } from '@tanstack/react-router'

import { AppRoute } from '../../../../app/AppRoute'
import { integrationsClient } from '../../../../client'
import { SynErrorState } from '../../../../components/states/SynErrorState'
import { useQueryState } from '../../../../components/states/useQueryState'
import { useUrlTab } from '../../../../hooks/useUrlTab'
import { detachPromise } from '../../../../utils/detachPromise'

import {
  IntegrationDetailContent,
  IntegrationDetailEarlyShell,
  type IntegrationDetailTab,
} from './IntegrationDetailContent'

export function IntegrationDetail() {
  const { integrationId }: { integrationId: string } = useParams({ strict: false })
  const integrationBasePath = AppRoute.Configuration.Integrations.Detail.replace(':integrationId', integrationId)
  const [activeTab] = useUrlTab<IntegrationDetailTab>(integrationBasePath)

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

  if (activeTab === 'edit') return null

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

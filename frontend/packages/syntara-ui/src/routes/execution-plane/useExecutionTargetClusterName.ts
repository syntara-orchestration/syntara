import { IntegrationTypeEnum } from '@syntara/contracts'

import { integrationsClient } from '../../client'

/**
 * Resolve the readonly OpenShift cluster display name for execution-target forms.
 * Shown only when exactly one OpenShift integration is installed.
 */
export function useExecutionTargetClusterName(): {
  clusterName: string | undefined
  isClusterPending: boolean
} {
  const clusterQuery = integrationsClient.useQuery('get', '/integrations', {
    params: {
      query: {
        integration_type: IntegrationTypeEnum.OPENSHIFT,
        limit: 1,
        include_total: true,
      },
    },
  })

  const openshiftIntegrations = clusterQuery.data?.resources
  const clusterName = clusterQuery.data?.total === 1 ? openshiftIntegrations?.[0]?.name?.trim() || undefined : undefined

  return {
    clusterName,
    isClusterPending: clusterQuery.isPending,
  }
}

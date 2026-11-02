import { IntegrationTypeEnum } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'

import { integrationsFetchClient } from '../../../../client'

/** Shared query key so create/delete can invalidate without stale create-form cache. */
export const OPENSHIFT_INTEGRATION_EXISTS_QUERY_KEY = ['openshift-integration-exists'] as const

async function fetchOpenShiftIntegrationExists(): Promise<boolean> {
  const result = await integrationsFetchClient.GET('/integrations', {
    params: {
      query: {
        integration_type: IntegrationTypeEnum.OPENSHIFT,
        limit: 1,
      },
    },
  })
  if (result.error) throw new Error(JSON.stringify(result.error))
  return (result.data?.resources?.length ?? 0) > 0
}

/**
 * Whether an openshift (Execution plane infrastructure) integration already exists.
 * Refetches on every mount so delete-then-recreate is not blocked by a stale cache.
 */
export function useOpenShiftIntegrationExists() {
  const {
    data: exists = false,
    isPending,
    isError,
    refetch,
  } = useQuery({
    queryKey: OPENSHIFT_INTEGRATION_EXISTS_QUERY_KEY,
    queryFn: fetchOpenShiftIntegrationExists,
    refetchOnMount: 'always',
  })

  return { exists, isLoading: isPending, isError, refetch }
}

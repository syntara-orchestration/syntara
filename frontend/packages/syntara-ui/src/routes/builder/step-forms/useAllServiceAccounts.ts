import type { ServiceAccountsAPI } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'

import { fetchAllPages, MAX_PAGE_SIZE } from '../../../utils/fetchAllPages'
import { accessFetchClient } from '../../access/accessClient'

type ServiceAccountRead = ServiceAccountsAPI.components['schemas']['ServiceAccountRead']

async function fetchAllServiceAccounts(projectId?: string | null): Promise<ServiceAccountRead[]> {
  return fetchAllPages<ServiceAccountRead>((cursor) =>
    accessFetchClient.GET('/service_accounts', {
      params: {
        query: { sort: 'name', limit: MAX_PAGE_SIZE, cursor, ...(projectId ? { project_id: projectId } : {}) },
      },
    })
  )
}

export function useAllServiceAccounts(projectId?: string | null) {
  const {
    data: serviceAccounts = [],
    isPending,
    refetch,
  } = useQuery({
    queryKey: ['all-service-accounts', projectId],
    queryFn: () => fetchAllServiceAccounts(projectId),
  })
  return { serviceAccounts, isLoading: isPending, refetch }
}

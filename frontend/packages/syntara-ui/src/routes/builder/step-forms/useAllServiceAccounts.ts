import type { ServiceAccountsAPI } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'

import { fetchAllPages, MAX_PAGE_SIZE } from '../../../utils/fetchAllPages'
import { accessFetchClient } from '../../access/accessClient'

type ServiceAccountDirectoryEntry = ServiceAccountsAPI.components['schemas']['ServiceAccountDirectoryEntry']

async function fetchAllServiceAccounts(): Promise<ServiceAccountDirectoryEntry[]> {
  return fetchAllPages<ServiceAccountDirectoryEntry>((cursor) =>
    accessFetchClient.GET('/service_accounts/directory', {
      params: {
        query: { sort: 'name', limit: MAX_PAGE_SIZE, cursor },
      },
    })
  )
}

export function useAllServiceAccounts() {
  const {
    data: serviceAccounts = [],
    isPending,
    refetch,
  } = useQuery({
    queryKey: ['all-service-accounts'],
    queryFn: () => fetchAllServiceAccounts(),
  })
  return { serviceAccounts, isLoading: isPending, refetch }
}

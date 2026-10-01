import type { UsersAPI } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'

import { usersFetchClient } from '../../../client'
import { fetchAllPages, MAX_PAGE_SIZE } from '../../../utils/fetchAllPages'

type GroupDirectoryEntry = UsersAPI.components['schemas']['GroupDirectoryEntry']

async function fetchAllGroupDirectory(): Promise<GroupDirectoryEntry[]> {
  return fetchAllPages<GroupDirectoryEntry>((cursor) =>
    usersFetchClient.GET('/groups/directory', {
      params: { query: { sort: 'name', limit: MAX_PAGE_SIZE, cursor } },
    })
  )
}

/**
 * Hook to fetch groups for the approval node approver-groups dropdown.
 *
 * Uses the lightweight `/groups/directory` endpoint (id + name only),
 * which is accessible to the `user` role via `group-directory:read`.
 * Note: groups are not filtered by approval:decide capability — the backend
 * validates group membership at decision time.
 */
export function useApprovalDecideGroups() {
  const {
    data: groups = [],
    isPending,
    error,
    refetch,
  } = useQuery({
    queryKey: ['approval-decide-groups'],
    queryFn: fetchAllGroupDirectory,
    refetchOnMount: 'always',
    refetchOnWindowFocus: false,
  })

  return {
    groups,
    isLoading: isPending,
    error,
    refetch,
  }
}

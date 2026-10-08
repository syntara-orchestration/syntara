import type { AuthzAPI } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'

import { fetchAllPages, MAX_PAGE_SIZE } from '../../../utils/fetchAllPages'
import { accessFetchClient } from '../../access/accessClient'

type WhoCanUser = AuthzAPI.components['schemas']['WhoCanUser']

class PermissionDeniedError extends Error {
  constructor() {
    super('Permission denied')
    this.name = 'PermissionDeniedError'
  }
}

export type UseWhoCanProjectUsersParams = {
  projectId?: string | null
  action: string
  resourceType: string
  queryKeyPrefix: string
}

/**
 * Fetch users authorized for a project-scoped (resource_type, action) pair via /authz/who_can.
 *
 * Disabled until projectId is set. Surfaces `isPermissionDenied` when the API returns
 * AUTHORIZATION_DENIED so callers can fall back to manual entry.
 */
export function useWhoCanProjectUsers({
  projectId,
  action,
  resourceType,
  queryKeyPrefix,
}: UseWhoCanProjectUsersParams) {
  async function fetchAllAuthorizedUsers(): Promise<WhoCanUser[]> {
    if (!projectId) {
      return []
    }

    return fetchAllPages<WhoCanUser>(async (cursor: string | undefined) => {
      const result = await accessFetchClient.POST('/authz/who_can', {
        body: {
          action,
          resource_type: resourceType,
          sort: 'username',
          limit: MAX_PAGE_SIZE,
          cursor,
          resource_project: projectId,
        },
      })

      if (result.error?.code === 'AUTHORIZATION_DENIED') {
        throw new PermissionDeniedError()
      }

      if (!result.data) {
        return { data: undefined, error: result.error }
      }

      return {
        data: result.data,
        error: result.error,
      }
    })
  }

  const {
    data: users = [],
    isPending,
    isFetching,
    error,
    refetch,
  } = useQuery({
    queryKey: [queryKeyPrefix, projectId],
    queryFn: fetchAllAuthorizedUsers,
    enabled: !!projectId,
    refetchOnMount: 'always',
    refetchOnWindowFocus: false,
    retry: (failureCount, err) => {
      if (err instanceof PermissionDeniedError) return false
      return failureCount < 3
    },
  })

  const isPermissionDenied = error instanceof PermissionDeniedError

  return {
    users,
    isLoading: isPending && isFetching,
    isPermissionDenied,
    error: isPermissionDenied ? null : error,
    refetch,
  }
}

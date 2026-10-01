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

/**
 * Hook to fetch all users who have approval:decide permission in a project.
 *
 * Uses /authz/who_can endpoint with cursor pagination to fetch all authorized users.
 * The query is disabled until a projectId is provided — the approval form shows a
 * "select a project" prompt in the meantime rather than firing an unscoped request.
 *
 * If the endpoint returns 403, the hook surfaces `isPermissionDenied: true` so the
 * UI can offer a manual-input fallback instead of an empty dropdown.
 *
 * @param projectId - Project ID to scope the permission check. The query does not
 *                    run until this is a non-empty string.
 * @returns Object containing users array, loading state, permission-denied flag, and error
 */
export function useApprovalDecideUsers(projectId?: string | null) {
  async function fetchAllApprovalDecideUsers(): Promise<WhoCanUser[]> {
    if (!projectId) {
      return []
    }

    return fetchAllPages<WhoCanUser>(async (cursor: string | undefined) => {
      const result = await accessFetchClient.POST('/authz/who_can', {
        body: {
          action: 'decide',
          resource_type: 'approval',
          sort: 'username',
          limit: MAX_PAGE_SIZE,
          cursor,
          resource_project: projectId,
        },
      })

      if (result.error?.code === 'AUTHORIZATION_DENIED') {
        throw new PermissionDeniedError()
      }

      // WhoCanResponse already has the correct shape {resources, next} for fetchAllPages
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
    queryKey: ['approval-decide-users', projectId],
    queryFn: fetchAllApprovalDecideUsers,
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

import { useQuery } from '@tanstack/react-query'

import { fetchAllPages, MAX_PAGE_SIZE } from '../../utils/fetchAllPages'

import { accessFetchClient } from './accessClient'
import type { RoleRead } from './types'

async function fetchAllProjectRoles(projectId: string): Promise<RoleRead[]> {
  return fetchAllPages<RoleRead>((cursor) =>
    accessFetchClient.GET('/projects/{project_id}/roles', {
      params: {
        path: { project_id: projectId },
        query: { sort: 'name', limit: MAX_PAGE_SIZE, cursor },
      },
    })
  )
}

/** All roles defined on a project (for assign-role modals). */
export function useAllProjectRoles(projectId: string | undefined) {
  const {
    data: roles = [],
    isPending,
    error,
    refetch,
  } = useQuery({
    queryKey: ['all-project-roles', projectId],
    queryFn: () => fetchAllProjectRoles(projectId ?? ''),
    enabled: !!projectId,
  })
  return { roles, isLoading: isPending, error, refetch }
}

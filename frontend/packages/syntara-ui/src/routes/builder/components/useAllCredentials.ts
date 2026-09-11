import { useQuery } from '@tanstack/react-query'

import { credentialsFetchClient } from '../../../client'
import { fetchAllPages, MAX_PAGE_SIZE } from '../../../utils/fetchAllPages'
import type { Credential } from '../../configuration/credentials/credentialConstants'

type UseAllCredentialsOptions = {
  /** Filter credentials to this project */
  projectId?: string
}

async function fetchAllCredentials({ projectId }: UseAllCredentialsOptions = {}): Promise<Credential[]> {
  return fetchAllPages<Credential>((cursor) =>
    credentialsFetchClient.GET('/credentials', {
      params: {
        query: {
          sort: 'name',
          for_action: 'use',
          limit: MAX_PAGE_SIZE,
          cursor,
          ...(projectId ? { project_id: projectId } : {}),
        },
      },
    })
  )
}

/**
 * Fetches the complete list of usable credentials, following pagination cursors
 * until every page has been retrieved (mirrors `useAllProjects` / `useAllIntegrationModels`).
 *
 * Use this instead of a single `credentialsClient.useQuery('get', '/credentials', ...)` call,
 * which only returns the first page and silently hides any credentials beyond it.
 */
export function useAllCredentials(options: UseAllCredentialsOptions = {}) {
  const { projectId } = options
  const {
    data: credentials = [],
    isPending,
    error,
    refetch,
  } = useQuery({
    queryKey: ['all-credentials', projectId],
    queryFn: () => fetchAllCredentials({ projectId }),
  })
  return { credentials, isLoading: isPending, error, refetch }
}

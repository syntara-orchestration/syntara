import { useQuery } from '@tanstack/react-query'

import { fetchAllPages, MAX_PAGE_SIZE } from '../../utils/fetchAllPages'

import { accessFetchClient } from './accessClient'
import type { ProjectRead } from './types'

function makeProjectFetcher(extra?: { is_builtin?: boolean }) {
  return async (): Promise<ProjectRead[]> =>
    fetchAllPages<ProjectRead>((cursor) =>
      accessFetchClient.GET('/projects', {
        params: { query: { sort: 'name', limit: MAX_PAGE_SIZE, cursor, ...extra } },
      })
    )
}

const fetchAllProjects = makeProjectFetcher()
const fetchSelectableProjects = makeProjectFetcher({ is_builtin: false })

type UseAllProjectsOptions = {
  /** When false, skips the fetch. Defaults to true. */
  enabled?: boolean
}

/** All projects, including the built-in project. Use for display and name-lookup contexts. */
export function useAllProjects(options?: UseAllProjectsOptions) {
  const enabled = options?.enabled ?? true
  const {
    data: projects = [],
    isPending,
    error,
    refetch,
  } = useQuery({
    queryKey: ['all-projects'],
    queryFn: fetchAllProjects,
    enabled,
  })
  return { projects, isLoading: enabled && isPending, error, refetch }
}

/** Non-builtin projects only. Use for "pick a project to create a resource in" dropdowns. */
export function useSelectableProjects(options?: UseAllProjectsOptions) {
  const enabled = options?.enabled ?? true
  const {
    data: projects = [],
    isPending,
    error,
    refetch,
  } = useQuery({
    queryKey: ['all-projects', { is_builtin: false }],
    queryFn: fetchSelectableProjects,
    enabled,
  })
  return { projects, isLoading: enabled && isPending, error, refetch }
}

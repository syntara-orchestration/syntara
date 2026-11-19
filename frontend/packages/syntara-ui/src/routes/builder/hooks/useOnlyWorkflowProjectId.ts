import { useMemo } from 'react'

import { PROJECTS_PAGE_SIZE } from '../../../hooks/usePaginatedProjects'
import { accessClient } from '../../access/accessClient'

/**
 * The id of the only project the caller can create workflows in, or `undefined`
 * when there are none, several, or the list is still loading.
 *
 * The new-workflow project picker defaults to it ("if only one project exists, it
 * is selected by default", R18 / AC-4.c). Built-in projects cannot hold workflows,
 * so they don't count. It reads the picker's unfiltered first page, so it shares
 * that cache entry and adds no request; a second page means several projects.
 */
export function useOnlyWorkflowProjectId(): string | undefined {
  const query = accessClient.useQuery('get', '/projects', { params: { query: { limit: PROJECTS_PAGE_SIZE } } })

  return useMemo(() => {
    if (!query.isSuccess || query.data.next) return undefined
    const selectable = query.data.resources.filter((project) => project.id && !project.is_builtin)
    return selectable.length === 1 ? (selectable[0].id ?? undefined) : undefined
  }, [query.isSuccess, query.data])
}

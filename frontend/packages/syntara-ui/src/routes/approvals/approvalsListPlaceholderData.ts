import type { Query } from '@tanstack/react-query'

type PaginatedListData = {
  next?: string | null
  prev?: string | null
  total?: number | null
}

/** Stable scope id for approvals list queries (all projects vs one project). */
export function getApprovalsListScopeKey(isAllProjects: boolean, stableProjectId: string | null | undefined): string {
  return isAllProjects ? 'all' : `project:${stableProjectId ?? ''}`
}

function getApprovalsScopeKeyFromQuery(query: Pick<Query, 'queryKey'> | Query): string {
  const path = query.queryKey[1]
  if (path === '/approvals') return 'all'
  if (path === '/projects/{project_id}/approvals') {
    const config = query.queryKey[2] as { params?: { path?: { project_id?: string } } } | undefined
    return `project:${config?.params?.path?.project_id ?? ''}`
  }
  return ''
}

/**
 * Keeps the previous page visible while sort/filter/cursor params change within the same scope.
 * Does not keep data when the project scope changes (project A → project B).
 */
export function createApprovalsListPlaceholderData<T>(
  currentScopeKey: string
): (previousData: T | undefined, previousQuery: Query) => T | undefined {
  return (previousData, previousQuery): T | undefined => {
    if (!previousData) return undefined
    if (getApprovalsScopeKeyFromQuery(previousQuery) !== currentScopeKey) return undefined
    return previousData
  }
}

/** While placeholder data is shown, drop stale cursor fields so pagination cannot advance on the wrong page. */
export function stripStaleListPaginationCursors<T extends PaginatedListData>(
  data: T | undefined,
  isPlaceholderData: boolean
): T | undefined {
  if (!data || !isPlaceholderData) return data
  // Drop cursor fields and total so footer pagination cannot advance on stale list metadata.
  return { ...data, next: null, prev: null, total: null }
}

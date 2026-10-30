import type { ActivityExecution } from '@syntara/contracts'
import { useQueries } from '@tanstack/react-query'

import { executionsClient } from '../../../../client'

import { type ChildExecution, useChildExecutions } from './useChildExecutions'

/** Max activities fetched per child in one page (see the pagination note on the hook). */
export const CHILD_ACTIVITIES_PAGE_LIMIT = 100

export type ChildExecutionActivities = {
  child: ChildExecution
  activities: ActivityExecution[]
  /** True when the child returned a full page, i.e. more activities may exist than fetched. */
  isTruncated: boolean
}

export type SubWorkflowChildData = {
  childData: ChildExecutionActivities[]
  isLoading: boolean
  isError: boolean
  /** True when any child's activity set was truncated at the page limit. */
  isTruncated: boolean
}

/**
 * Read-only composition of a sub-workflow node's child execution(s) and each
 * child's persisted activities, for display-time enrichment. Reuses the existing
 * ``/children`` lookup and ``/activities`` endpoint (one query per child, via
 * ``useQueries``); because the query keys match, these share TanStack Query's
 * cache with the Child activities tab rather than refetching.
 *
 * Pagination: each child's activities are requested one page deep
 * (``CHILD_ACTIVITIES_PAGE_LIMIT``). A full page sets ``isTruncated`` so callers
 * can surface that not all activities are shown; deeper retrieval would require
 * cursor pagination (not added here).
 */
export function useSubWorkflowChildData(
  parentExecutionId: string | null | undefined,
  nodeId: string
): SubWorkflowChildData {
  const { children, isLoading: childrenLoading, isError: childrenError } = useChildExecutions(parentExecutionId, nodeId)

  const activityResults = useQueries({
    queries: children.map((child) =>
      executionsClient.queryOptions('get', '/executions/{execution_id}/activities', {
        params: { path: { execution_id: child.id }, query: { limit: CHILD_ACTIVITIES_PAGE_LIMIT } },
      })
    ),
  })

  const childData: ChildExecutionActivities[] = children.map((child, index) => {
    const result = activityResults[index]
    const activities = (result?.data?.resources ?? []) as ActivityExecution[]
    return {
      child,
      activities,
      isTruncated: activities.length >= CHILD_ACTIVITIES_PAGE_LIMIT,
    }
  })

  return {
    childData,
    isLoading: childrenLoading || activityResults.some((result) => result.isLoading),
    isError: childrenError || activityResults.some((result) => result.isError),
    isTruncated: childData.some((entry) => entry.isTruncated),
  }
}

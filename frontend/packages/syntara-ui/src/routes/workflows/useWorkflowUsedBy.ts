import type { WorkflowAPI } from '@syntara/contracts'
import { createContext, use, useMemo } from 'react'

import { workflowClient } from '../../client'

export type ReferencingParent = WorkflowAPI.components['schemas']['WorkflowRead']

type UseWorkflowUsedByOptions = {
  enabled?: boolean
  /** Restrict the result to parents that invoke any of these child Subworkflow Trigger nodes. */
  triggerNodeIds?: string[]
  /** Cursor for the page to fetch (drives the Used-By drill-down modal's pagination). */
  cursor?: string
  /** Page size; defaults to the API default when omitted. */
  limit?: number
}

/**
 * Used-By for a single workflow: how many published parents reference it (unfiltered total),
 * plus the RBAC-filtered page of parents the caller may view. ``next``/``prev`` are the cursors
 * for paging through the visible parents (used by the drill-down modal).
 */
export function useWorkflowUsedBy(workflowId: string | undefined, options: UseWorkflowUsedByOptions = {}) {
  const enabled = (options.enabled ?? true) && !!workflowId
  const query = workflowClient.useQuery(
    'get',
    '/workflows/{workflow_id}/used_by',
    {
      params: {
        path: { workflow_id: workflowId ?? '' },
        query: {
          ...(options.triggerNodeIds?.length ? { trigger_node_ids: options.triggerNodeIds } : {}),
          ...(options.cursor ? { cursor: options.cursor } : {}),
          ...(options.limit ? { limit: options.limit } : {}),
        },
      },
    },
    { enabled }
  )

  return {
    totalCount: query.data?.referencing_parent_count ?? 0,
    referencingParents: (query.data?.resources ?? []) as ReferencingParent[],
    next: query.data?.next ?? null,
    prev: query.data?.prev ?? null,
    isLoading: query.isLoading && enabled,
    isError: !!query.error,
  }
}

/**
 * Batch Used-By totals for a page of workflows in a single request (avoids one call per row).
 * ``workflowIds`` should be a stable/memoized array so the query is not refetched needlessly.
 */
export function useWorkflowUsedByCounts(workflowIds: string[], options: { enabled?: boolean } = {}) {
  const enabled = (options.enabled ?? true) && workflowIds.length > 0
  const query = workflowClient.useQuery(
    'get',
    '/workflows/used_by_counts',
    { params: { query: { workflow_ids: workflowIds } } },
    { enabled }
  )

  const countsById = useMemo(() => {
    const map = new Map<string, number>()
    for (const entry of query.data?.counts ?? []) {
      map.set(entry.workflow_id, entry.referencing_parent_count)
    }
    return map
  }, [query.data])

  return { countsById, isLoading: query.isLoading && enabled, isError: !!query.error }
}

/**
 * Per-workflow Used-By totals for the current list page, provided once by the list container so
 * each row reads its count without issuing its own request. Defaults to an empty map, so a row
 * rendered outside the provider simply shows no count.
 */
export const WorkflowUsedByCountsContext = createContext<Map<string, number>>(new Map())

export function useWorkflowUsedByCountsContext(): Map<string, number> {
  return use(WorkflowUsedByCountsContext)
}

/**
 * Convenience hook for a workflow list page: derives the (capped, memoized) id set from the
 * visible workflows and returns their Used-By totals as a map keyed by workflow id.
 */
export function useVisibleUsedByCounts(workflows: { id: string }[]): Map<string, number> {
  const workflowIds = useMemo(() => workflows.slice(0, 100).map((workflow) => workflow.id), [workflows])
  return useWorkflowUsedByCounts(workflowIds).countsById
}

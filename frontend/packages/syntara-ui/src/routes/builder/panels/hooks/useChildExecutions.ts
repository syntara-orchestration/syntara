import { executionsClient } from '../../../../client'
import { detachPromise } from '../../../../utils/detachPromise'

/**
 * Lists the child (sub-workflow) executions of a parent execution's node, via the
 * read-only ``GET /executions/{execution_id}/children`` lookup. Requests the total
 * count so the panel can disclose when the first page does not show every child,
 * and exposes ``refetch`` so a transient failure can be retried in place.
 */
export function useChildExecutions(parentExecutionId: string | null | undefined, nodeId: string) {
  const pageSize = 100
  const query = executionsClient.useQuery(
    'get',
    '/executions/{execution_id}/children',
    {
      params: {
        path: { execution_id: parentExecutionId ?? '' },
        query: { node_id: nodeId, limit: pageSize, include_total: true },
      },
    },
    { enabled: Boolean(parentExecutionId) && Boolean(nodeId) }
  )

  const children = query.data?.resources ?? []
  const total = query.data?.total ?? null

  return {
    children,
    total,
    hasMore: typeof total === 'number' ? total > children.length : children.length >= pageSize,
    isLoading: query.isLoading,
    isError: query.isError,
    refetch: () => {
      detachPromise(query.refetch())
    },
  }
}

export type ChildExecution = ReturnType<typeof useChildExecutions>['children'][number]

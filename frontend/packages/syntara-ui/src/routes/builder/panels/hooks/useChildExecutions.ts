import { executionsClient } from '../../../../client'

/**
 * Lists the child (sub-workflow) executions of a parent execution's node, via the
 * read-only ``GET /executions/{execution_id}/children`` lookup. A ``for_each``
 * sub-workflow node yields one child per iteration (up to the 100-row page size;
 * more than that would need cursor pagination). Enabled only in execution view
 * (when a ``parentExecutionId`` is present).
 */
export function useChildExecutions(parentExecutionId: string | null | undefined, nodeId: string) {
  const query = executionsClient.useQuery(
    'get',
    '/executions/{execution_id}/children',
    { params: { path: { execution_id: parentExecutionId ?? '' }, query: { node_id: nodeId, limit: 100 } } },
    { enabled: Boolean(parentExecutionId) && Boolean(nodeId) }
  )

  return {
    children: query.data?.resources ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
  }
}

export type ChildExecution = ReturnType<typeof useChildExecutions>['children'][number]

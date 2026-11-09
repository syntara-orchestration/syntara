import { useMemo } from 'react'

import * as routeRefs from '../../../app/routes/routeReferences'
import { executionsClient } from '../../../client'
import { useCursorPagination } from '../../../hooks/useCursorPagination'
import { transformExecutionStatusFilter } from '../executionFilters'

/** Cursor pagination, sort, and list query for the Run History panel on execution detail. */
export function useExecutionRunHistory(workflowId: string | undefined) {
  const executionExtraParams = useMemo(() => ({ workflow_id: workflowId ?? '' }), [workflowId])

  const {
    filters: executionFilters,
    queryParams: executionsQueryParams,
    handleFilterChange: handleExecutionFilterChange,
    getFooterProps: getExecutionPaginationFooterProps,
  } = useCursorPagination({
    limit: 20,
    transformFilters: transformExecutionStatusFilter,
    extraParams: executionExtraParams,
    defaultSort: { field: 'created_at', direction: 'desc' as const },
  })

  const executionsQuery = executionsClient.useQuery(
    'get',
    routeRefs.executionsListRoute.fullPath,
    {
      params: { query: executionsQueryParams },
    },
    {
      enabled: !!workflowId,
    }
  )

  const executionPaginationFooterProps = useMemo(
    () => getExecutionPaginationFooterProps(executionsQuery.data),
    [getExecutionPaginationFooterProps, executionsQuery.data]
  )

  return {
    executionFilters,
    handleExecutionFilterChange,
    executionsQuery,
    executionPaginationFooterProps,
  }
}

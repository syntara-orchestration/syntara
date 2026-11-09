import type { FetchOptions, FetchResponse } from 'openapi-fetch'
import type { HttpMethod, MediaType, PathsWithMethod, RequiredKeysOf } from 'openapi-typescript-helpers'
import type React from 'react'
import { useMemo } from 'react'

import type { QueryStateOptions } from '../components/states/useQueryState'
import { useQueryState } from '../components/states/useQueryState'
import type { FilterConfig } from '../types/filters'
import { buildFilterParams } from '../utils/filterUtils'

/**
 * Options for useFilteredQuery hook
 */
export type UseFilteredQueryOptions<
  Paths extends Record<string, Record<HttpMethod, object>>,
  Method extends HttpMethod,
  Path extends PathsWithMethod<Paths, Method>,
> = {
  /** API client (e.g., workflowClient, executionsClient) */
  client: {
    useQuery: <
      M extends HttpMethod,
      P extends PathsWithMethod<Paths, M>,
      Init extends FetchOptions<FilterPaths<Paths, P, M>>,
    >(
      method: M,
      path: P,
      ...init: RequiredKeysOf<FetchOptions<FilterPaths<Paths, P, M>>> extends never
        ? [(FetchOptions<FilterPaths<Paths, P, M>> | undefined)?]
        : [FetchOptions<FilterPaths<Paths, P, M>>]
    ) => {
      data: FetchResponse<FilterPaths<Paths, P, M>, Init, MediaType>['data']
      error: FetchResponse<FilterPaths<Paths, P, M>, Init, MediaType>['error']
      isPending: boolean
      refetch: () => void
    }
  }
  /** HTTP method (e.g., 'get') */
  method: Method
  /** API endpoint path (e.g., '/workflows') */
  path: Path
  /** Active filters */
  filters?: FilterConfig[]
  /** Sort parameter (e.g., 'name', '-created_at') */
  sort?: string
  /** Results per page limit */
  limit?: number
  /** Pagination cursor */
  cursor?: string | null
  /** Whether to include total count in response */
  includeTotalCount?: boolean
  /** Error state options */
  errorOptions?: QueryStateOptions
}

// Helper type to extract the paths from the client
type FilterPaths<Paths, Path, Method> =
  Paths extends Record<string, Record<string, object>>
    ? Path extends keyof Paths
      ? Method extends keyof Paths[Path]
        ? Paths[Path][Method]
        : never
      : never
    : never

/**
 * Result from useFilteredQuery hook
 */
export type UseFilteredQueryResult<TData> = {
  /** Query response data */
  data: TData | undefined
  /** Query error */
  error: unknown
  /** Whether query is loading */
  isPending: boolean
  /** Refetch query */
  refetch: () => void
  /** Loading/error state component (null if data ready) */
  queryState: React.ReactElement | null
}

/**
 * Hook for executing filtered API queries with automatic query parameter building
 *
 * Integrates filters with React Query to provide type-safe, filtered API queries.
 * Automatically converts FilterConfig[] to API query parameters and handles
 * loading/error states with useQueryState.
 *
 * @param options - Query configuration options
 * @returns Query result with data, loading, error states, and refetch function
 *
 * @example
 * ```typescript
 * function WorkflowsPage() {
 *   const { filters } = useFilterState()
 *
 *   const { data, queryState, refetch } = useFilteredQuery({
 *     client: workflowClient,
 *     method: 'get',
 *     path: '/workflows',
 *     filters,
 *     limit: 20,
 *     includeTotalCount: true,
 *     errorOptions: {
 *       title: 'Error loading workflows',
 *       onRetry: () => refetch()
 *     }
 *   })
 *
 *   // Show loading/error state
 *   if (queryState) return queryState
 *
 *   // Render data
 *   const workflows = data?.resources ?? []
 *   return <WorkflowList workflows={workflows} />
 * }
 * ```
 *
 * @example
 * ```typescript
 * // With sort and pagination
 * const { data, queryState } = useFilteredQuery({
 *   client: executionsClient,
 *   method: 'get',
 *   path: routeRefs.executionsListRoute.fullPath,
 *   filters: [
 *     { key: 'workflow_id', operator: 'eq', value: workflowId },
 *     { key: 'status', operator: 'in', value: ['running', 'failed'] }
 *   ],
 *   sort: '-created_at',
 *   limit: 50,
 *   cursor: nextCursor,
 *   includeTotalCount: true,
 *   errorOptions: { title: 'Error loading executions' }
 * })
 * ```
 */
export function useFilteredQuery<
  Paths extends Record<string, Record<HttpMethod, object>>,
  Method extends HttpMethod,
  Path extends PathsWithMethod<Paths, Method>,
>(
  options: UseFilteredQueryOptions<Paths, Method, Path>
): UseFilteredQueryResult<FetchResponse<FilterPaths<Paths, Path, Method>, object, MediaType>['data']> {
  const { client, method, path, filters = [], sort, limit, cursor, includeTotalCount = false, errorOptions } = options

  // Build query parameters from filters
  const queryParams = useMemo(() => {
    const params: Record<string, unknown> = {}

    // Add filter params
    const filterParams = buildFilterParams(filters)
    Object.assign(params, filterParams)

    // Add sort param if provided
    if (sort) {
      params.sort = sort
    }

    // Add pagination params
    if (limit !== undefined) {
      params.limit = limit
    }

    if (cursor !== undefined && cursor !== null) {
      params.cursor = cursor
    }

    // Add total count param
    if (includeTotalCount) {
      params.include_total = true
    }

    return params
  }, [filters, sort, limit, cursor, includeTotalCount])

  // Execute query with built parameters
  // Type assertion needed due to complex openapi-react-query generic constraints
  // The queryParams are properly typed from buildFilterParams, but the client's
  // generic signature doesn't perfectly align with our dynamic params approach
  const query = client.useQuery(method, path, {
    params: {
      query: queryParams,
    },
  } as FetchOptions<FilterPaths<Paths, Path, Method>>)

  // Get loading/error state component
  const queryState = useQueryState(query, errorOptions)

  return {
    data: query.data as FetchResponse<FilterPaths<Paths, Path, Method>, object, MediaType>['data'] | undefined,
    error: query.error,
    isPending: query.isPending,
    refetch: query.refetch,
    queryState,
  }
}

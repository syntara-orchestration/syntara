import type { WorkflowAPI } from '@syntara/contracts'
import { ExecutionStatusEnum } from '@syntara/contracts'

import { workflowFetchClient } from '../../client'
import type { FilterConfig, FilterFieldDefinition } from '../../types/filters'
import { FilterTypeEnum } from '../../types/filters'
import { formatDateTime } from '../../utils/dateUtils'
import { executionStatusDisplayLabels } from '../builder/executionStatusConstants'

/**
 * Transforms workflow resources into filter options
 * Exported for testing purposes
 * @internal
 */
export function transformWorkflowsToOptions(
  workflows: Array<{ id?: string | null; name?: string | null }>
): Array<{ value: string; label: string }> {
  return workflows
    .map((workflow) => ({
      value: workflow.id ?? '',
      label: workflow.name ?? '',
    }))
    .filter((opt) => opt.value && opt.label)
}

/**
 * Returns filter definition for filtering executions by workflow with server-side typeahead
 *
 * @returns FilterFieldDefinition configured for workflow filtering with async SELECT type
 *
 * @remarks
 * Uses server-side typeahead via asyncOptions to support filtering by any workflow,
 * not just the first page of results. Queries /workflows with name[contains] parameter.
 * Uses the shared authenticated workflowFetchClient from client.tsx.
 *
 * @example
 * ```typescript
 * const filterDef = getExecutionWorkflowFilterDefinition()
 * // User types "deploy" → queries /workflows?name[contains]=deploy
 * // Generates query param: workflow_id=workflow-123
 * ```
 */
export const getExecutionWorkflowFilterDefinition = (): FilterFieldDefinition => ({
  key: 'workflow_id',
  label: 'Workflow name',
  type: FilterTypeEnum.SELECT,
  asyncOptions: async (searchValue: string) => {
    const params: Record<string, unknown> = {
      limit: 50,
    }

    if (searchValue.trim()) {
      params['name[contains]'] = searchValue.trim()
    }

    try {
      const response = await workflowFetchClient.GET('/workflows', {
        params: { query: params as WorkflowAPI.paths['/workflows']['get']['parameters']['query'] },
      })

      const workflows = response.data?.resources ?? []
      return transformWorkflowsToOptions(workflows)
    } catch {
      return []
    }
  },
  placeholder: 'Search workflows',
})

/**
 * Returns filter definition for filtering executions by status.
 * Includes a synthetic "Pending approval" option that maps to approval_pending=true.
 *
 * @returns FilterFieldDefinition configured for status filtering with SELECT type
 *
 * @remarks
 * Uses SELECT (single selection) instead of MULTISELECT because the backend API
 * does not currently support the status[in] operator for multiple status values.
 * When backend support is added, this can be changed to FilterTypeEnum.MULTISELECT
 * to allow filtering by multiple statuses at once.
 *
 * @example
 * ```typescript
 * const filterDef = getExecutionStatusFilterDefinition()
 * // Generates query param: status=completed
 * // "Pending approval" → transformExecutionStatusFilter → approval_pending=true
 * ```
 */
/** Sentinel status value for runs awaiting approval (maps to approval_pending=true, not status=). */
export const EXECUTION_STATUS_APPROVAL_PENDING = 'approval_pending'

const EXECUTION_STATUS_OPTIONS = [
  ...Object.values(ExecutionStatusEnum)
    .filter((status): status is keyof typeof executionStatusDisplayLabels => status in executionStatusDisplayLabels)
    .map((status) => ({
      value: status,
      label: executionStatusDisplayLabels[status],
    })),
  { value: EXECUTION_STATUS_APPROVAL_PENDING, label: 'Pending approval' },
]

export const getExecutionStatusFilterDefinition = (): FilterFieldDefinition => ({
  key: 'status',
  label: 'Status',
  type: FilterTypeEnum.SELECT,
  options: EXECUTION_STATUS_OPTIONS,
  placeholder: 'Filter by status',
})

/**
 * Maps the synthetic "Pending approval" status selection to approval_pending=true.
 * Other status filters pass through unchanged.
 */
export const transformExecutionStatusFilter = (filters: FilterConfig[]): FilterConfig[] =>
  filters.flatMap((filter) =>
    filter.key === 'status' && filter.value === EXECUTION_STATUS_APPROVAL_PENDING
      ? [{ key: 'approval_pending', value: true }]
      : [filter]
  )

type ExecutionWithVersion = {
  workflow_version_id?: string
  workflow_version_name?: string | null
  workflow_version_created_at?: string | null
}

export function getExecutionVersionFilterFromExecutions(executions: ExecutionWithVersion[]): FilterFieldDefinition {
  const seen = new Map<string, string>()
  for (const exec of executions) {
    const id = exec.workflow_version_id
    if (id && !seen.has(id)) {
      seen.set(id, exec.workflow_version_name ?? formatDateTime(exec.workflow_version_created_at ?? ''))
    }
  }
  const options = Array.from(seen.entries()).map(([value, label]) => ({ value, label }))
  return {
    key: 'workflow_version_id',
    label: 'Version',
    type: FilterTypeEnum.SELECT,
    options,
    getOptionLabel: (value: string) => seen.get(value),
    placeholder: 'Filter by version',
  }
}

/**
 * Returns filter definition for filtering executions by creation date range
 *
 * @returns null - Currently disabled due to backend limitation
 *
 * @remarks
 * **DISABLED DUE TO BACKEND LIMITATION**: The API currently uses OR logic instead of AND
 * for date range queries. For example:
 * - Query: `created_at[gte]=2026-03-16&created_at[lte]=2026-03-18`
 * - Current behavior: Returns executions BEFORE 2026-03-18 OR AFTER 2026-03-16 (incorrect)
 * - Expected behavior: Returns executions BETWEEN 2026-03-16 AND 2026-03-18 (correct)
 *
 * This filter is hidden until the backend bug is fixed. To re-enable after backend fix,
 * change return type to FilterFieldDefinition and uncomment the implementation below.
 *
 * @example
 * ```typescript
 * // When backend is fixed, uncomment:
 * // const filterDef = getExecutionCreatedAtFilterDefinition()
 * // Generates query params:
 * // created_at[gte]=2026-03-16T00:00:00.000Z
 * // created_at[lte]=2026-03-18T23:59:59.999Z
 * ```
 */
export const getExecutionCreatedAtFilterDefinition = (): null => {
  // Disabled due to backend OR logic bug - uncomment when fixed:
  // return {
  //   key: 'created_at',
  //   label: 'Created Date',
  //   type: FilterTypeEnum.DATERANGE,
  //   operators: [FilterOperatorEnum.GTE, FilterOperatorEnum.LTE],
  //   placeholder: 'Filter by creation date',
  // }
  return null
}

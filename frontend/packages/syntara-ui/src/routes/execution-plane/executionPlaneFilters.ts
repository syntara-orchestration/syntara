import type { FilterFieldDefinition } from '../../types/filters'
import { FilterOperatorEnum, FilterTypeEnum } from '../../types/filters'
import { capitalize } from '../../utils/capitalize'

/**
 * Canonical execution-target statuses from EP `TargetStatus`
 * (`syntara-execution-plane` → `execution_plane.models.execution_target.TargetStatus`).
 */
export const EXECUTION_TARGET_STATUS_VALUES = [
  'registering',
  'validating',
  'bootstrapping',
  'active',
  'degraded',
  'draining',
  'failed',
] as const

export const getExecutionTargetNameFilterDefinition = (): FilterFieldDefinition => ({
  key: 'name',
  label: 'Name',
  type: FilterTypeEnum.TEXT,
  operators: [FilterOperatorEnum.CONTAINS],
  defaultOperator: FilterOperatorEnum.CONTAINS,
  placeholder: 'Filter by name',
})

/**
 * Status filter — MULTISELECT + IN (`status[in]=active,degraded`), same pattern as Approvals.
 * EP documents `eq` and `in` for status; values must match `TargetStatus`.
 */
export const getExecutionTargetStatusFilterDefinition = (): FilterFieldDefinition => ({
  key: 'status',
  label: 'Status',
  type: FilterTypeEnum.MULTISELECT,
  operators: [FilterOperatorEnum.IN],
  defaultOperator: FilterOperatorEnum.IN,
  options: EXECUTION_TARGET_STATUS_VALUES.map((value) => ({
    value,
    label: capitalize(value.replaceAll('_', ' ')),
  })),
  placeholder: 'Filter by status',
})

/**
 * State filter — SELECT with string `'true'`/`'false'` (Identity Providers / Workflows pattern).
 * EP OpenAPI types `enabled` as a string query param; no boolean transform needed.
 */
export const getExecutionTargetEnabledFilterDefinition = (): FilterFieldDefinition => ({
  key: 'enabled',
  label: 'State',
  type: FilterTypeEnum.SELECT,
  options: [
    { value: 'true', label: 'Enabled' },
    { value: 'false', label: 'Disabled' },
  ],
  placeholder: 'Filter by state',
})

/**
 * Last run date range — DATERANGE → `last_ran_at[gte]` / `last_ran_at[lte]`.
 * EP documents range operators for last_ran_at.
 */
export const getExecutionTargetLastRanAtFilterDefinition = (): FilterFieldDefinition => ({
  key: 'last_ran_at',
  label: 'Last run',
  type: FilterTypeEnum.DATERANGE,
  operators: [FilterOperatorEnum.GTE, FilterOperatorEnum.LTE],
  placeholder: 'Filter by last run',
})

/** All Execution Plane list filter definitions (order matches FilterBar attribute list). */
export const getExecutionPlaneFilterDefinitions = (): FilterFieldDefinition[] => [
  getExecutionTargetNameFilterDefinition(),
  getExecutionTargetStatusFilterDefinition(),
  getExecutionTargetEnabledFilterDefinition(),
  getExecutionTargetLastRanAtFilterDefinition(),
]

import type { ExecutionPlaneAPI } from '@syntara/contracts'

import type { FilterConfig } from '../../types/filters'

export type ExecutionTarget = ExecutionPlaneAPI.components['schemas']['ExecutionTargetFacadeRead']

/**
 * Client-side name filter for the Execution Plane list.
 * The facade list endpoint only accepts `limit` today (no sort/filter query params).
 */
export function filterExecutionTargets(targets: ExecutionTarget[], filters: FilterConfig[]): ExecutionTarget[] {
  const nameFilter = filters.find((filter) => filter.key === 'name')
  const nameQuery = typeof nameFilter?.value === 'string' ? nameFilter.value.trim().toLowerCase() : ''

  if (!nameQuery) return targets

  return targets.filter((target) => target.name.toLowerCase().includes(nameQuery))
}

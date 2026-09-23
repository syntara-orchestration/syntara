import type { FilterConfig, FilterFieldDefinition } from '../../types/filters'
import { FilterTypeEnum } from '../../types/filters'

/** Sentinel value used in scope filter to represent system-scoped items (no project) */
const SYSTEM_SCOPE_VALUE = '__system__'

/** Scope options for the Policies tab (backend values: any, self, project) */
export const POLICY_SCOPE_OPTIONS = [
  { value: 'any', label: 'Any' },
  { value: 'self', label: 'Self' },
  { value: 'project', label: 'Project' },
]

/** Scope options for the Roles tab (backend values: system, project) */
export { roleAssignmentScopeOptions as ROLE_SCOPE_OPTIONS } from '../access-management/RoleAssignmentTypes'

/**
 * Builds scope filter field definitions with dynamic project options.
 * Returns a new array with the scope field's options populated from the project name map.
 */
export function buildFilterDefsWithScope(
  baseDefs: FilterFieldDefinition[],
  projectNameMap: Map<string, string>
): FilterFieldDefinition[] {
  const projectOptions = Array.from(projectNameMap.entries()).map(([id, name]) => ({
    value: id,
    label: name,
  }))

  return baseDefs.map((def) => {
    if (def.key === 'scope' && def.type === FilterTypeEnum.SELECT) {
      return { ...def, options: [{ value: SYSTEM_SCOPE_VALUE, label: 'System' }, ...projectOptions] }
    }
    return def
  })
}

/**
 * Builds project filter field definitions with dynamic project options.
 */
export function buildProjectFilterDefs(
  baseDefs: FilterFieldDefinition[],
  projectNameMap: Map<string, string>
): FilterFieldDefinition[] {
  const projectOptions = Array.from(projectNameMap.entries()).map(([id, name]) => ({
    value: id,
    label: name,
  }))

  return baseDefs.map((def) => {
    if (def.key === 'project' && def.type === FilterTypeEnum.SELECT) {
      return { ...def, options: projectOptions }
    }
    return def
  })
}

/**
 * Transforms UI filter configs into API-compatible filter configs.
 * - Maps `type` filter to `is_builtin`
 * - Maps `scope` filter directly to `scope` query param
 * - Maps `project` filter to `project_id` query param
 */
export function transformFiltersForApi(filters: FilterConfig[]): FilterConfig[] {
  return filters.map((f) => {
    if (f.key === 'type') {
      return { key: 'is_builtin', value: f.value === 'builtin' }
    }
    if (f.key === 'project') {
      return { key: 'project_id', value: f.value }
    }
    return f
  })
}

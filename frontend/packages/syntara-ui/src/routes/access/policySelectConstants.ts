/** Minimal policy fields used by role policy pickers and select-all fetching. */
export type PolicySelectListItem = {
  name: string
  description?: string | null
  project_id?: string | null
  is_project_eligible: boolean
}

/** Sentinel value for the "Select All" action in policy multi-select dropdowns. */
export const SELECT_ALL_VALUE = '__select_all__'

/** Label for the select-all menu action (matches MultiSelectFilter). */
export const SELECT_ALL_LABEL = 'Select all'

export const SELECT_ALL_LOAD_ERROR = {
  title: 'Failed to load policies',
  description: 'Could not select all policies. Try again.',
} as const

export type PolicySelectScopeParams = {
  scopeProjectId?: string | null
  projectEligible?: boolean
}

/** Keep only policies assignable to the current role scope. */
export function filterPoliciesForRoleSelect<T extends PolicySelectListItem>(
  policies: T[],
  { scopeProjectId, projectEligible }: PolicySelectScopeParams
): T[] {
  if (scopeProjectId) {
    return policies.filter((policy) => policy.project_id == null || policy.project_id === scopeProjectId)
  }

  if (projectEligible) {
    return policies.filter((policy) => policy.is_project_eligible)
  }

  return policies.filter((policy) => !policy.is_project_eligible)
}

/** Merge currently selected policy names with all option names (deduped). */
export function mergeSelectAll(currentSelected: string[], optionNames: string[]): string[] {
  return [...new Set([...currentSelected, ...optionNames])]
}

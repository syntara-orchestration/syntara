import { fetchAllPages, MAX_PAGE_SIZE } from '../../utils/fetchAllPages'

import { accessFetchClient } from './accessClient'
import { toPolicySelectPageResult } from './policySelectApi'
import {
  filterPoliciesForRoleSelect,
  type PolicySelectListItem,
  type PolicySelectScopeParams,
} from './policySelectConstants'

export type FetchAllPoliciesParams = PolicySelectScopeParams & {
  nameContains?: string
}

/** Fetch every policy matching the role-select query (all pages). */
export async function fetchAllPoliciesForSelect({
  scopeProjectId,
  projectEligible,
  nameContains,
}: FetchAllPoliciesParams): Promise<PolicySelectListItem[]> {
  const policies = await fetchAllPages<PolicySelectListItem>(async (cursor) =>
    toPolicySelectPageResult(
      await accessFetchClient.GET('/policies', {
        params: {
          query: {
            sort: 'name',
            limit: MAX_PAGE_SIZE,
            cursor,
            ...(nameContains ? { 'name[contains]': nameContains } : {}),
            ...(scopeProjectId ? { project_id: scopeProjectId } : {}),
            ...(projectEligible ? { project_eligible: true } : {}),
          },
        },
      })
    )
  )

  return filterPoliciesForRoleSelect(policies, { scopeProjectId, projectEligible })
}

/** Fetch every project policy, optionally narrowed by a client-side name filter. */
export async function fetchAllProjectPoliciesForSelect(
  projectId: string,
  nameContains?: string
): Promise<PolicySelectListItem[]> {
  const allPolicies = await fetchAllPages<PolicySelectListItem>(async (cursor) =>
    toPolicySelectPageResult(
      await accessFetchClient.GET('/projects/{project_id}/policies', {
        params: {
          path: { project_id: projectId },
          query: { sort: 'name', limit: MAX_PAGE_SIZE, cursor },
        },
      })
    )
  )

  if (!nameContains) return allPolicies

  const term = nameContains.toLowerCase()
  return allPolicies.filter((policy) => policy.name.toLowerCase().includes(term))
}

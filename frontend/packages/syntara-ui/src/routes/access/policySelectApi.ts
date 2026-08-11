import type { FetchPageResult } from '../../utils/fetchAllPages'

import type { PolicySelectListItem } from './policySelectConstants'

type PolicyListPayload = {
  resources?:
    | readonly {
        name: string
        description?: string | null
        project_id?: string | null
        is_project_eligible: boolean
      }[]
    | null
  next?: string | null
}

/** Map an openapi-fetch list response to policy-select list items without unsafe casts. */
export function toPolicySelectPageResult(result: {
  data?: PolicyListPayload
  error?: unknown
}): FetchPageResult<PolicySelectListItem> {
  const { data, error } = result
  if (error) return { error }
  if (!data) return { error: 'Empty response' }

  return {
    data: {
      next: data.next,
      resources: (data.resources ?? []).map((policy) => ({
        name: policy.name,
        description: policy.description,
        project_id: policy.project_id,
        is_project_eligible: policy.is_project_eligible,
      })),
    },
  }
}

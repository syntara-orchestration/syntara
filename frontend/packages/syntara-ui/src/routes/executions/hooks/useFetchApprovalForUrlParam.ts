import type { Approval } from '@syntara/contracts'

import { approvalsClient } from '../../../client'

function isApproval(data: unknown): data is Approval {
  return typeof data === 'object' && data !== null && 'id' in data && typeof data.id === 'string'
}

export type UseFetchApprovalForUrlParamResult = {
  approval: Approval | undefined
  error: unknown
  isPending: boolean
}

/**
 * Reads a `?approval=<approvalId>` URL search param and fetches the approval.
 * Returns the fetched approval and query error so the caller can react to both.
 *
 * Used when deep-linking from the approvals list page to the execution viewer.
 */
export function useFetchApprovalForUrlParam(searchParams: string): UseFetchApprovalForUrlParamResult {
  const approvalId = new URLSearchParams(searchParams).get('approval')

  const approvalQuery = approvalsClient.useQuery(
    'get',
    '/approvals/{approval_id}',
    { params: { path: { approval_id: approvalId ?? '' } } },
    { enabled: !!approvalId }
  )

  return {
    approval: isApproval(approvalQuery.data) ? approvalQuery.data : undefined,
    error: approvalQuery.error ?? undefined,
    isPending: approvalQuery.isPending,
  }
}

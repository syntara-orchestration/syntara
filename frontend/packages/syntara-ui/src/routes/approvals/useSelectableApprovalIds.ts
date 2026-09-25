import { useMemo } from 'react'

import { usersClient } from '../../client'
import { useAuthStore } from '../../stores/useAuthStore'

import type { ApprovalWithDetails } from './Approvals'
import { computeCanDecideOnApproval } from './computeCanDecideOnApproval'
import { isApprovalSelectable } from './isApprovalSelectable'

/**
 * Hook to compute which approvals are selectable (checkbox should be enabled) for select-all logic.
 * Uses the same logic as individual row rendering in ApprovalsTableBody.
 *
 * @param sortedApprovals - List of approvals to check
 * @param approvalPermissions - Map of approval ID to RBAC permission
 * @param isLoadingDecideProjects - Whether RBAC permissions are still loading
 * @returns Set of approval IDs that are selectable
 */
export function useSelectableApprovalIds(
  sortedApprovals: ApprovalWithDetails[],
  approvalPermissions: Map<string, boolean>,
  isLoadingDecideProjects: boolean
): Set<string> {
  // Fetch current user's groups for approver list checks
  const currentUsername = useAuthStore((state) => state.username)
  const currentUserId = useAuthStore((state) => state.userId)

  const userGroupsQuery = usersClient.useQuery('get', '/users/{user_id}/groups', {
    params: { path: { user_id: currentUserId ?? '' } },
    enabled: Boolean(currentUserId),
  })

  const isLoadingUserGroups = userGroupsQuery?.isLoading ?? false

  // Compute which approvals are selectable
  return useMemo(() => {
    const set = new Set<string>()

    // Map user groups to minimal shape for approver list checks
    const userGroupsForCheck = (userGroupsQuery?.data?.resources ?? [])
      .filter((g): g is { id: string; name: string } => Boolean(g.id && g.name))
      .map((g) => ({ id: g.id, name: g.name }))

    for (const approval of sortedApprovals) {
      const canDecideOnThisApproval = approvalPermissions.get(approval.id) ?? false
      const canDecideBasedOnApproverList = computeCanDecideOnApproval(approval, currentUsername, userGroupsForCheck)

      if (
        isApprovalSelectable({
          approval,
          canDecideOnThisApproval,
          canDecideBasedOnApproverList,
          isLoadingPermissions: isLoadingDecideProjects,
          isCheckingApproverList: isLoadingUserGroups,
        })
      ) {
        set.add(approval.id)
      }
    }

    return set
  }, [
    sortedApprovals,
    approvalPermissions,
    isLoadingDecideProjects,
    currentUsername,
    userGroupsQuery?.data?.resources,
    isLoadingUserGroups,
  ])
}

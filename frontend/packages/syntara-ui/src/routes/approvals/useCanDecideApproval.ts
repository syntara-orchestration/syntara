import type { Approval } from '@syntara/contracts'
import { useMemo } from 'react'

import { usersClient } from '../../client'
import { useAuthStore } from '../../stores/useAuthStore'

/**
 * Hook to check if the current user can decide on a specific approval.
 *
 * SECURITY NOTE: This is a UX-only check to disable UI controls. The backend
 * ALWAYS validates authorization and returns 403 for unauthorized users.
 * See syntara/approvals/services/approval_service.py:_is_user_authorized_approver()
 *
 * Authorization logic:
 * 1. If no approvers configured (both lists empty), any user with approval:decide permission can approve
 * 2. If approver_users configured, checks if current username is in the list
 * 3. If approver_groups configured, fetches user's groups and checks membership
 *
 * @param approval - The approval to check authorization for (or undefined while loading)
 * @returns object - {canDecide: boolean, isLoading: boolean}
 */
export function useCanDecideApproval(
  approval: Partial<Pick<Approval, 'approver_users' | 'approver_groups'>> | undefined
): { canDecide: boolean; isLoading: boolean } {
  const currentUsername = useAuthStore((state) => state.username)
  const currentUserId = useAuthStore((state) => state.userId)

  // Extract approver configuration
  const approverUsers = approval?.approver_users
  const approverGroups = approval?.approver_groups

  // Determine if we need to check group membership
  const hasApprovers = (approverUsers && approverUsers.length > 0) || (approverGroups && approverGroups.length > 0)
  const isDirectMatch = Boolean(
    currentUsername && approverUsers?.some((user: { username: string }) => user.username === currentUsername)
  )
  const needsGroupCheck =
    hasApprovers && !isDirectMatch && approverGroups && approverGroups.length > 0 && Boolean(currentUserId)

  // Fetch user's groups to check membership (using userId from JWT, no need to query /users first)
  const groupsQuery = usersClient.useQuery('get', '/users/{user_id}/groups', {
    params: { path: { user_id: currentUserId ?? '' } },
    enabled: needsGroupCheck,
  })

  const result = useMemo(() => {
    // If approval not loaded yet, conservatively disallow
    if (!approval) {
      return { canDecide: false, isLoading: false }
    }

    // If neither field is present in the object (empty object), treat as invalid
    if (!('approver_users' in approval) && !('approver_groups' in approval)) {
      return { canDecide: false, isLoading: false }
    }

    // If no approvers configured at all, allow (permission check happens elsewhere)
    if (!hasApprovers) {
      return { canDecide: true, isLoading: false }
    }

    // If current user is in approver_users list, allow
    if (isDirectMatch) {
      return { canDecide: true, isLoading: false }
    }

    // If we don't need to check groups (user not in users list, no groups configured), deny
    if (!needsGroupCheck) {
      return { canDecide: false, isLoading: false }
    }

    // While loading groups data, show loading state
    if (groupsQuery?.isLoading) {
      return { canDecide: false, isLoading: true }
    }

    // Check if user is member of any approver group (by ID to handle renames)
    const userGroups = groupsQuery?.data?.resources ?? []
    const userGroupIds = new Set(userGroups.map((g) => g.id))
    const isGroupMember = approverGroups.some((group: { id: string }) => userGroupIds.has(group.id))

    return { canDecide: isGroupMember, isLoading: false }
  }, [
    approval,
    hasApprovers,
    isDirectMatch,
    needsGroupCheck,
    groupsQuery?.isLoading,
    groupsQuery?.data,
    approverGroups,
  ])

  return result
}

/**
 * Pure utility function to determine if the current user can decide on an approval
 * based on approver list configuration (approver_users and approver_groups).
 *
 * This is the core logic extracted from useCanDecideApproval hook, made reusable
 * for both per-row checks and bulk select-all operations.
 *
 * Authorization logic:
 * 1. If no approvers configured (both lists empty/absent) → allow
 * 2. If current user in approver_users list → allow
 * 3. If current user in any of the approver_groups → allow
 * 4. Otherwise → deny
 *
 * SECURITY NOTE: This is a UX-only check. The backend ALWAYS validates and returns 403.
 * See syntara/approvals/services/approval_service.py:_is_user_authorized_approver()
 */

import type { ApprovalWithDetails } from './Approvals'

export function computeCanDecideOnApproval(
  approval: ApprovalWithDetails,
  currentUsername: string | null,
  userGroups: ReadonlyArray<{ id: string; name: string }>
): boolean {
  const approverUsers = approval.approver_users
  const approverGroups = approval.approver_groups

  // No approvers configured → allow (permission check happens via RBAC)
  if (!approverUsers?.length && !approverGroups?.length) {
    return true
  }

  // Check if current user is in approver_users list
  if (currentUsername && approverUsers?.some((user) => user.username === currentUsername)) {
    return true
  }

  // Check if current user is member of any approver_groups (by ID to handle renames)
  if (approverGroups && approverGroups.length > 0) {
    const userGroupIds = new Set(userGroups.map((g) => g.id))
    if (approverGroups.some((group) => userGroupIds.has(group.id))) {
      return true
    }
  }

  return false
}

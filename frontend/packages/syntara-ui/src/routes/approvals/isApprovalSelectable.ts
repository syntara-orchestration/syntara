import type { ApprovalWithDetails } from './Approvals'

/**
 * Determines if an approval is selectable (checkbox should be enabled).
 * Used by both individual row rendering and select-all logic.
 *
 * @returns true if the approval checkbox should be enabled, false if disabled
 */
export function isApprovalSelectable({
  approval,
  canDecideOnThisApproval,
  canDecideBasedOnApproverList,
  isLoadingPermissions,
  isCheckingApproverList,
}: {
  approval: ApprovalWithDetails
  canDecideOnThisApproval: boolean
  canDecideBasedOnApproverList: boolean
  isLoadingPermissions: boolean
  isCheckingApproverList: boolean
}): boolean {
  // Not pending → not selectable
  if (approval.status !== 'pending') return false

  // Still loading → not selectable
  if (isLoadingPermissions || isCheckingApproverList) return false

  // Missing RBAC permission or not on approver list → not selectable
  if (!canDecideOnThisApproval || !canDecideBasedOnApproverList) return false

  return true
}

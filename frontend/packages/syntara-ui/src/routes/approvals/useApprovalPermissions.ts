import { useMemo } from 'react'

import { permissionTooltip } from '../../hooks/permissionUtils'
import { useCanI } from '../../hooks/useCanI'

import { useApprovalDecideProjects } from './useApprovalDecideProjects'

/**
 * Domain hook for approval-related permissions.
 *
 * Aggregates permission checks for approval read and decide actions,
 * following the pattern established in useWorkflowPermissions, useCredentialPermissions, etc.
 *
 * @param projectId - Optional project ID for project-scoped permission checks
 * @returns Object containing:
 *   - canRead: true if user has approval:read permission
 *   - canDecide: true if user has approval:decide permission (global or project-scoped)
 *   - isChecking: true while any permission check is loading
 *   - tooltips: Standard tooltip content for disabled actions
 *
 * @example
 * ```tsx
 * // Global permission check
 * const permissions = useApprovalPermissions()
 *
 * // Project-scoped permission check
 * const permissions = useApprovalPermissions(approval.project_id)
 *
 * if (permissions.isChecking) return <Spinner />
 * if (!permissions.canRead) return <SynEmptyStateAccessDenied />
 *
 * <DisabledWithTooltip isDisabled={!permissions.canDecide} content={permissions.tooltips.decide}>
 *   <Button isAriaDisabled={!permissions.canDecide} onClick={permissions.canDecide ? handleDecide : undefined}>
 *     Approve
 *   </Button>
 * </DisabledWithTooltip>
 * ```
 */
export function useApprovalPermissions(projectId?: string | null) {
  const canReadGlobalQuery = useCanI('read', 'approval')
  const canDecideGlobalQuery = useCanI('decide', 'approval')

  const { canDecideProjectNames, canReadProjectNames, isLoading: isLoadingProjectPerms } = useApprovalDecideProjects()

  return useMemo(() => {
    const hasProjectDecide = projectId ? canDecideProjectNames.has(projectId) : false
    const canDecide = canDecideGlobalQuery.allowed || hasProjectDecide

    const hasProjectRead = projectId ? canReadProjectNames.has(projectId) : canReadProjectNames.size > 0
    const canRead = canReadGlobalQuery.allowed || hasProjectRead

    return {
      canRead,
      canDecide,
      isChecking: canReadGlobalQuery.isChecking || canDecideGlobalQuery.isChecking || isLoadingProjectPerms,
      tooltips: {
        decide: permissionTooltip('decide on approvals', 'approval:decide'),
      },
    }
  }, [
    canReadGlobalQuery.allowed,
    canReadGlobalQuery.isChecking,
    canDecideGlobalQuery.allowed,
    canDecideGlobalQuery.isChecking,
    canDecideProjectNames,
    canReadProjectNames,
    isLoadingProjectPerms,
    projectId,
  ])
}

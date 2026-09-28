import { useCanI } from '../../../hooks/useCanI'

type ProjectDetailPermissions = {
  canReadWorkflows: boolean
  canReadAssignments: boolean
  isLoading: boolean
}

/**
 * Permission checks for project detail page tabs.
 *
 * Scoped to the concrete project so a grant in another project does not unlock
 * the Workflows or Assignments tabs here.
 */
export function useProjectDetailPermissions(resourceProject: string): ProjectDetailPermissions {
  const enabled = Boolean(resourceProject)
  const { allowed: canReadWorkflows, isChecking: isCheckingWorkflows } = useCanI('read', 'workflow', {
    resourceProject,
    enabled,
  })
  const { allowed: canReadAssignments, isChecking: isCheckingAssignments } = useCanI('read', 'role-assignment', {
    resourceProject,
    enabled,
  })

  return {
    canReadWorkflows,
    canReadAssignments,
    isLoading: isCheckingWorkflows || isCheckingAssignments,
  }
}

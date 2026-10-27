import { permissionTooltip } from '../../hooks/permissionUtils'
import { useCanI } from '../../hooks/useCanI'

type ExecutionTargetPermissions = {
  canCreate: boolean
  isLoading: boolean
  tooltips: {
    create: string
  }
}

/**
 * Permission checks for execution target management actions.
 *
 * Checks: execution_target:create. Defaults to `false` until the check resolves.
 */
export function useExecutionTargetPermissions(): ExecutionTargetPermissions {
  const resourceType = 'execution_target' as const
  const { allowed: canCreate, isChecking } = useCanI('create', resourceType)

  return {
    canCreate,
    isLoading: isChecking,
    tooltips: {
      create: permissionTooltip('configure an execution target', `${resourceType}:create`),
    },
  }
}

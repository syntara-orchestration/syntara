import { useMemo } from 'react'

import { permissionTooltip } from '../../hooks/permissionUtils'
import { useCanI } from '../../hooks/useCanI'

export type ExecutionTargetPermissions = {
  canCreate: boolean
  canUpdate: boolean
  canDelete: boolean
  isLoading: boolean
  tooltips: {
    create: string
    update: string
    delete: string
  }
}

/**
 * Permission checks for execution target management actions.
 *
 * Checks: execution_target:create, execution_target:update, execution_target:delete.
 * Defaults to `false` until each check resolves.
 */
export function useExecutionTargetPermissions(): ExecutionTargetPermissions {
  const resourceType = 'execution_target' as const
  const { allowed: canCreate, isChecking: isCheckingCreate } = useCanI('create', resourceType)
  const { allowed: canUpdate, isChecking: isCheckingUpdate } = useCanI('update', resourceType)
  const { allowed: canDelete, isChecking: isCheckingDelete } = useCanI('delete', resourceType)

  return useMemo(
    () => ({
      canCreate,
      canUpdate,
      canDelete,
      isLoading: isCheckingCreate || isCheckingUpdate || isCheckingDelete,
      tooltips: {
        create: permissionTooltip('configure an execution target', `${resourceType}:create`),
        update: permissionTooltip('edit this execution target', `${resourceType}:update`),
        delete: permissionTooltip('delete this execution target', `${resourceType}:delete`),
      },
    }),
    [canCreate, canUpdate, canDelete, isCheckingCreate, isCheckingUpdate, isCheckingDelete]
  )
}

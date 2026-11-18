import { useMemo } from 'react'

import { permissionTooltip, useResourceCrudPermissions } from '../../hooks/permissionUtils'
import { useCanI } from '../../hooks/useCanI'

export type ExecutionTargetPermissions = {
  canRead: boolean
  canCreate: boolean
  canUpdate: boolean
  canDelete: boolean
  isLoading: boolean
  tooltips: {
    read: string
    create: string
    update: string
    enable: string
    delete: string
  }
}

/**
 * Permission checks for execution target management and builder selection.
 *
 * Checks: execution_target:read, create, update, delete.
 * Defaults to `false` until each check resolves.
 */
export function useExecutionTargetPermissions(): ExecutionTargetPermissions {
  const resourceType = 'execution_target' as const
  const { allowed: canRead, isChecking: isCheckingRead } = useCanI('read', resourceType)
  const { canCreate, canUpdate, canDelete, isLoading: isLoadingCrud } = useResourceCrudPermissions(resourceType)
  const updatePermission = `${resourceType}:update`

  return useMemo<ExecutionTargetPermissions>(
    () => ({
      canRead,
      canCreate,
      canUpdate,
      canDelete,
      isLoading: isCheckingRead || isLoadingCrud,
      tooltips: {
        read: permissionTooltip('list execution targets', `${resourceType}:read`),
        create: permissionTooltip('configure an execution target', `${resourceType}:create`),
        update: permissionTooltip('edit this execution target', updatePermission),
        enable: permissionTooltip('enable or disable this execution target', updatePermission),
        delete: permissionTooltip('delete this execution target', `${resourceType}:delete`),
      },
    }),
    [canRead, canCreate, canUpdate, canDelete, isCheckingRead, isLoadingCrud, updatePermission]
  )
}

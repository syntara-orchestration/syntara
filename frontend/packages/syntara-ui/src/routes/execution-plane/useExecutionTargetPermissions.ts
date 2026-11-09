import { useMemo } from 'react'

import { permissionTooltip, useResourceCrudPermissions } from '../../hooks/permissionUtils'

export type ExecutionTargetPermissions = {
  canCreate: boolean
  canUpdate: boolean
  canDelete: boolean
  isLoading: boolean
  tooltips: {
    create: string
    update: string
    enable: string
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
  const { canCreate, canUpdate, canDelete, isLoading } = useResourceCrudPermissions(resourceType)
  const updatePermission = `${resourceType}:update`

  return useMemo(
    () => ({
      canCreate,
      canUpdate,
      canDelete,
      isLoading,
      tooltips: {
        create: permissionTooltip('configure an execution target', `${resourceType}:create`),
        update: permissionTooltip('edit this execution target', updatePermission),
        enable: permissionTooltip('enable or disable this execution target', updatePermission),
        delete: permissionTooltip('delete this execution target', `${resourceType}:delete`),
      },
    }),
    [canCreate, canUpdate, canDelete, isLoading, updatePermission]
  )
}

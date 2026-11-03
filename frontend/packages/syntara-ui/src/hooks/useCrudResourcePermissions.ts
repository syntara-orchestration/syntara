import { permissionTooltip } from './permissionUtils'
import { useCanI } from './useCanI'

type CanICheckConfig = {
  options?: {
    resourceProject?: string
    enabled?: boolean
  }
}

export type CrudResourcePermissions = {
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

type UseCrudResourcePermissionsParams = {
  resourceType: string
  tooltipTargets: {
    create: string
    update: string
    delete: string
  }
  createCheck: CanICheckConfig
  updateCheck: CanICheckConfig
  deleteCheck: CanICheckConfig
}

function useCanICheck(action: string, resourceType: string, config: CanICheckConfig) {
  const { options } = config
  const enabled = options?.enabled ?? true
  return useCanI(action, resourceType, { ...options, enabled })
}

/**
 * Shared create/update/delete permission checks for a single resource type.
 * Callers configure per-action `useCanI` options (scoped project, enabled gates, etc.).
 */
export function useCrudResourcePermissions({
  resourceType,
  tooltipTargets,
  createCheck,
  updateCheck,
  deleteCheck,
}: UseCrudResourcePermissionsParams): CrudResourcePermissions {
  const { allowed: canCreate, isChecking: isCheckingCreate } = useCanICheck('create', resourceType, createCheck)
  const { allowed: canUpdate, isChecking: isCheckingUpdate } = useCanICheck('update', resourceType, updateCheck)
  const { allowed: canDelete, isChecking: isCheckingDelete } = useCanICheck('delete', resourceType, deleteCheck)

  return {
    canCreate,
    canUpdate,
    canDelete,
    isLoading: isCheckingCreate || isCheckingUpdate || isCheckingDelete,
    tooltips: {
      create: permissionTooltip(tooltipTargets.create, `${resourceType}:create`),
      update: permissionTooltip(tooltipTargets.update, `${resourceType}:update`),
      delete: permissionTooltip(tooltipTargets.delete, `${resourceType}:delete`),
    },
  }
}

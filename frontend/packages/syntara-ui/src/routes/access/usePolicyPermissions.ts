import { permissionTooltip } from '../../hooks/permissionUtils'
import { useCanI } from '../../hooks/useCanI'

type PolicyPermissions = {
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

type UsePolicyPermissionsOptions = {
  /** When set, check policy creation against this concrete project. */
  resourceProject?: string
}

export function usePolicyPermissions(options?: UsePolicyPermissionsOptions): PolicyPermissions {
  const resourceType = 'policy' as const
  const canIOptions = options?.resourceProject ? { resourceProject: options.resourceProject } : undefined
  const { allowed: canCreate, isChecking: isCheckingCreate } = useCanI('create', resourceType, canIOptions)
  const { allowed: canUpdate, isChecking: isCheckingUpdate } = useCanI('update', resourceType, canIOptions)
  const { allowed: canDelete, isChecking: isCheckingDelete } = useCanI('delete', resourceType, canIOptions)

  return {
    canCreate,
    canUpdate,
    canDelete,
    isLoading: isCheckingCreate || isCheckingUpdate || isCheckingDelete,
    tooltips: {
      create: permissionTooltip('create a policy', `${resourceType}:create`),
      update: permissionTooltip('edit this policy', `${resourceType}:update`),
      delete: permissionTooltip('delete this policy', `${resourceType}:delete`),
    },
  }
}

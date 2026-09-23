import { permissionTooltip } from '../../hooks/permissionUtils'
import { useCanI } from '../../hooks/useCanI'

type PolicyPermissions = {
  canCreate: boolean
  isLoading: boolean
  tooltips: {
    create: string
  }
}

type UsePolicyPermissionsOptions = {
  /** When set, check policy creation against this concrete project. */
  resourceProject?: string
}

export function usePolicyPermissions(options?: UsePolicyPermissionsOptions): PolicyPermissions {
  const resourceType = 'policy' as const
  const canIOptions = options?.resourceProject ? { resourceProject: options.resourceProject } : undefined
  const { allowed: canCreate, isChecking } = useCanI('create', resourceType, canIOptions)

  return {
    canCreate,
    isLoading: isChecking,
    tooltips: {
      create: permissionTooltip('create a policy', `${resourceType}:create`),
    },
  }
}

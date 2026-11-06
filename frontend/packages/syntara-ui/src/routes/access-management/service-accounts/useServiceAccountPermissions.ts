import { useMemo } from 'react'

import { permissionTooltip } from '../../../hooks/permissionUtils'
import { useCanI } from '../../../hooks/useCanI'

type ServiceAccountPermissions = {
  canCreate: boolean
  canUpdate: boolean
  canDelete: boolean
  canRotateSecret: boolean
  canEnable: boolean
  canDisable: boolean
  isLoading: boolean
  isError: boolean
  tooltips: {
    create: string
    update: string
    delete: string
    rotateSecret: string
  }
}

type UseServiceAccountPermissionsOptions = {
  resourceId?: string
}

export function useServiceAccountPermissions(options?: UseServiceAccountPermissionsOptions): ServiceAccountPermissions {
  const resourceType = 'service_account' as const
  const resourceId = options?.resourceId
  const destructiveOptions = { resourceId, enabled: Boolean(resourceId) }

  const { allowed: canCreate, isChecking: isCheckingCreate, isError: isErrorCreate } = useCanI('create', resourceType)
  const {
    allowed: canUpdate,
    isChecking: isCheckingUpdate,
    isError: isErrorUpdate,
  } = useCanI('update', resourceType, destructiveOptions)
  const {
    allowed: canDelete,
    isChecking: isCheckingDelete,
    isError: isErrorDelete,
  } = useCanI('delete', resourceType, destructiveOptions)
  const {
    allowed: canRotateSecret,
    isChecking: isCheckingRotate,
    isError: isErrorRotate,
  } = useCanI('rotate_secret', resourceType, destructiveOptions)

  const {
    allowed: canEnable,
    isChecking: isCheckingEnable,
    isError: isErrorEnable,
  } = useCanI('enable', resourceType, destructiveOptions)
  const {
    allowed: canDisable,
    isChecking: isCheckingDisable,
    isError: isErrorDisable,
  } = useCanI('disable', resourceType, destructiveOptions)

  return useMemo(
    () => ({
      canCreate,
      canUpdate,
      canDelete,
      canRotateSecret,
      canEnable,
      canDisable,
      isLoading:
        isCheckingCreate ||
        isCheckingUpdate ||
        isCheckingDelete ||
        isCheckingRotate ||
        isCheckingEnable ||
        isCheckingDisable,
      isError: isErrorCreate || isErrorUpdate || isErrorDelete || isErrorRotate || isErrorEnable || isErrorDisable,
      tooltips: {
        create: permissionTooltip('create a service account', `${resourceType}:create`),
        update: permissionTooltip('edit this service account', `${resourceType}:update`),
        delete: permissionTooltip('delete this service account', `${resourceType}:delete`),
        rotateSecret: permissionTooltip('rotate this credential secret', `${resourceType}:rotate_secret`),
      },
    }),
    [
      canCreate,
      canUpdate,
      canDelete,
      canRotateSecret,
      canEnable,
      canDisable,
      isCheckingCreate,
      isCheckingUpdate,
      isCheckingDelete,
      isCheckingRotate,
      isCheckingEnable,
      isCheckingDisable,
      isErrorCreate,
      isErrorUpdate,
      isErrorDelete,
      isErrorRotate,
      isErrorEnable,
      isErrorDisable,
    ]
  )
}

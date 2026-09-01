import { useMemo } from 'react'

import { permissionTooltip } from '../../../hooks/permissionUtils'
import { useCanI } from '../../../hooks/useCanI'

type CredentialPermissions = {
  canCreate: boolean
  canRead: boolean
  canUpdate: boolean
  canDelete: boolean
  /** `true` while any permission check (read/create/update/delete) is in flight. */
  isLoading: boolean
  /** `true` while only the read check is in flight. Use for access gates that should not wait on write checks. */
  isReadChecking: boolean
  tooltips: {
    create: string
    read: string
    update: string
    enable: string
    delete: string
  }
}

type UseCredentialPermissionsOptions = {
  /**
   * Concrete project to scope the permission check. The list toolbar passes
   * the selected project; each `CredentialRow` passes `credential.project_id`
   * for per-row gating in the "All projects" view. When omitted, create uses
   * `check_any_project` and update/delete fall back to system-scoped `can_i`
   * so system admins keep row actions.
   */
  resourceProject?: string
  /**
   * Skip all permission checks when false. Returns safe-false values with
   * `isLoading: true`. Use when the project_id is not yet available (e.g.
   * detail page while the credential query is in flight) to avoid a
   * system-scoped check that briefly shows a denied state.
   */
  enabled?: boolean
}

/**
 * Permission checks for credential actions.
 *
 * Checks: credential:read, credential:create, credential:update, credential:delete.
 * All values default to `false` (safe-false) until the checks resolve.
 *
 * @note All authorization checks require backend enforcement on credential endpoints.
 * Client-side permission gates are for UX only; backend MUST verify READ, CREATE, UPDATE,
 * DELETE permissions on GET, POST, PATCH, DELETE endpoints respectively.
 */
export function useCredentialPermissions(options?: UseCredentialPermissionsOptions): CredentialPermissions {
  const resourceType = 'credential' as const
  const resourceProject = options?.resourceProject
  const hasProject = Boolean(resourceProject)
  const enabled = options?.enabled ?? true

  const createOptions = hasProject ? { resourceProject, enabled } : { checkAnyProject: true as const, enabled }
  const scopedOptions = hasProject ? { resourceProject, enabled } : { enabled }

  const { allowed: canRead, isChecking: isCheckingRead } = useCanI('read', resourceType, scopedOptions)
  const { allowed: canCreate, isChecking: isCheckingCreate } = useCanI('create', resourceType, createOptions)
  const { allowed: canUpdate, isChecking: isCheckingUpdate } = useCanI('update', resourceType, scopedOptions)
  const { allowed: canDelete, isChecking: isCheckingDelete } = useCanI('delete', resourceType, scopedOptions)

  return useMemo(
    () => ({
      canRead,
      canCreate,
      canUpdate,
      canDelete,
      isLoading: !enabled || isCheckingRead || isCheckingCreate || isCheckingUpdate || isCheckingDelete,
      isReadChecking: !enabled || isCheckingRead,
      tooltips: {
        create: permissionTooltip('create a credential', 'credential:create'),
        read: permissionTooltip('view this credential', 'credential:read'),
        update: permissionTooltip('edit this credential', 'credential:update'),
        enable: permissionTooltip('enable or disable this credential', 'credential:update'),
        delete: permissionTooltip('delete this credential', 'credential:delete'),
      },
    }),
    [
      canRead,
      canCreate,
      canUpdate,
      canDelete,
      enabled,
      isCheckingRead,
      isCheckingCreate,
      isCheckingUpdate,
      isCheckingDelete,
    ]
  )
}

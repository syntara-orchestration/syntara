import { useMemo } from 'react'

import { permissionTooltip } from '../../hooks/permissionUtils'
import { useCanI } from '../../hooks/useCanI'

type WorkflowPermissions = {
  canCreate: boolean
  canUpdate: boolean
  canDelete: boolean
  canRun: boolean
  isLoading: boolean
  tooltips: {
    create: string
    duplicate: string
    update: string
    delete: string
    run: string
  }
}

type UseWorkflowPermissionsOptions = {
  /**
   * Concrete project when the workflows list has one selected. Create uses
   * `check_any_project` when omitted (toolbar on "All projects"); update /
   * delete / run fall back to system-scoped `can_i` so system admins keep row
   * actions. Prefer per-row `resourceProject` when adding stricter All-projects
   * gating later.
   */
  resourceProject?: string
}

/**
 * Permission checks for workflow list page actions.
 *
 * Checks: workflow:create, workflow:update, workflow:delete, execution:run.
 * All values default to `false` (safe-false) until the checks resolve.
 */
export function useWorkflowPermissions(options?: UseWorkflowPermissionsOptions): WorkflowPermissions {
  const resourceType = 'workflow' as const
  const resourceProject = options?.resourceProject
  const hasProject = Boolean(resourceProject)

  // Create: any-project when the list has no selected project (project-admin can
  // still open the builder). Update/delete/run: concrete project when selected,
  // otherwise system-scoped (same as pre-AAP-83790 for admin row actions).
  const createOptions = hasProject ? { resourceProject } : { checkAnyProject: true as const }
  const scopedOptions = hasProject ? { resourceProject } : undefined

  const { allowed: canCreate, isChecking: isCheckingCreate } = useCanI('create', resourceType, createOptions)
  const { allowed: canUpdate, isChecking: isCheckingUpdate } = useCanI('update', resourceType, scopedOptions)
  const { allowed: canDelete, isChecking: isCheckingDelete } = useCanI('delete', resourceType, scopedOptions)
  const { allowed: canRun, isChecking: isCheckingRun } = useCanI('run', 'execution', scopedOptions)

  return useMemo(
    () => ({
      canCreate,
      canUpdate,
      canDelete,
      canRun,
      isLoading: isCheckingCreate || isCheckingUpdate || isCheckingDelete || isCheckingRun,
      tooltips: {
        create: permissionTooltip('create a workflow', `${resourceType}:create`),
        duplicate: permissionTooltip('duplicate this workflow', `${resourceType}:create`),
        update: permissionTooltip('edit this workflow', `${resourceType}:update`),
        delete: permissionTooltip('delete this workflow', `${resourceType}:delete`),
        run: permissionTooltip('run this workflow', 'execution:run'),
      },
    }),
    [canCreate, canUpdate, canDelete, canRun, isCheckingCreate, isCheckingUpdate, isCheckingDelete, isCheckingRun]
  )
}

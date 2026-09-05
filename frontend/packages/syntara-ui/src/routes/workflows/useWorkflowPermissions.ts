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
   * Concrete project for `can_i`. Toolbar Create uses `check_any_project` when
   * omitted (All projects). Row kebabs must pass the workflow's `project_id`
   * so project-admin grants match on All projects.
   */
  resourceProject?: string
  /**
   * Skip update/delete/run checks. Use on the list page so the toolbar only
   * fetches Create; row kebabs call this hook with `resourceProject` instead.
   */
  createOnly?: boolean
  /**
   * When false, skip all `can_i` calls (safe-false). Row kebabs pass false until
   * the menu opens so All projects does not fire one request per visible row.
   */
  enabled?: boolean
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
  const checksEnabled = options?.enabled !== false
  const createEnabled = options?.createOnly === true || checksEnabled
  const rowChecksEnabled = options?.createOnly !== true && checksEnabled

  // Create: any-project when the list has no selected project (project-admin can
  // still open the builder). Update/delete/run: always pass a concrete project
  // for row kebabs; skip those queries when this hook is create-only (toolbar)
  // or until the row kebab opens (`enabled: false`).
  const createOptions = {
    ...(hasProject ? { resourceProject } : { checkAnyProject: true as const }),
    enabled: createEnabled,
  }
  const scopedOptions = {
    ...(hasProject ? { resourceProject } : {}),
    enabled: rowChecksEnabled,
  }

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

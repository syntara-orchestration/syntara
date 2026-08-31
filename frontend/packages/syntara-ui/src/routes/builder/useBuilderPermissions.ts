import { useMemo } from 'react'

import { permissionTooltip } from '../../hooks/permissionUtils'
import { useCanI } from '../../hooks/useCanI'

export type BuilderPermissions = {
  canEdit: boolean
  canCreate: boolean
  canRun: boolean
  canDelete: boolean
  isLoading: boolean
  tooltips: {
    edit: string
    save: string
    publish: string
    unpublish: string
    run: string
    delete: string
    create: string
  }
}

/**
 * Aggregates permission checks for the workflow builder.
 *
 * For new workflows `canEdit` reflects `workflow:create`;
 * for existing workflows it reflects `workflow:update`.
 * All values default to `false` (safe-false) until the checks resolve,
 * so the builder starts in read-only mode until permissions confirm edit access.
 *
 * Pass `projectId` so project-scoped grants (`workflow:create:project`,
 * `workflow:update:project`, etc.) are evaluated via `resourceProject`.
 * For new workflows without a selected project yet, create uses
 * `checkAnyProject` so project-user/project-admin are not stuck read-only
 * before picking a project. Update/delete/run stay project-scoped only.
 */
export function useBuilderPermissions(
  isNew: boolean,
  isBuiltin = false,
  projectId?: string | null
): BuilderPermissions {
  const createOptions = projectId ? { resourceProject: projectId } : { checkAnyProject: true as const }
  const scopedOptions = projectId ? { resourceProject: projectId } : undefined

  const { allowed: canCreate, isChecking: c1 } = useCanI('create', 'workflow', createOptions)
  const { allowed: canUpdate, isChecking: c2 } = useCanI('update', 'workflow', scopedOptions)
  const { allowed: canDelete, isChecking: c3 } = useCanI('delete', 'workflow', scopedOptions)
  const { allowed: canRun, isChecking: c4 } = useCanI('run', 'execution', scopedOptions)

  return useMemo(() => {
    const isLoading = c1 || c2 || c3 || c4
    const rbacCanEdit = isNew ? canCreate : canUpdate
    const canEdit = isBuiltin ? false : rbacCanEdit
    const editTooltip = isNew
      ? permissionTooltip('create a workflow', 'workflow:create')
      : permissionTooltip('edit this workflow', 'workflow:update')
    const saveTooltip = isNew
      ? permissionTooltip('save a new workflow', 'workflow:create')
      : permissionTooltip('save changes to this workflow', 'workflow:update')

    return {
      canEdit,
      canCreate: isBuiltin ? false : canCreate,
      canRun,
      canDelete: isBuiltin ? false : canDelete,
      isLoading,
      tooltips: {
        edit: editTooltip,
        save: saveTooltip,
        publish: permissionTooltip('publish this workflow', 'workflow:update'),
        unpublish: permissionTooltip('unpublish this workflow', 'workflow:update'),
        run: permissionTooltip('run this workflow', 'execution:run'),
        delete: permissionTooltip('delete this workflow', 'workflow:delete'),
        create: permissionTooltip('duplicate this workflow', 'workflow:create'),
      },
    }
  }, [isNew, isBuiltin, canCreate, canUpdate, canDelete, canRun, c1, c2, c3, c4])
}

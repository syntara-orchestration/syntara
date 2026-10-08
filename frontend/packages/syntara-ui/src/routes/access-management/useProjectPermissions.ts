import { useCrudResourcePermissions } from '../../hooks/useCrudResourcePermissions'

type ProjectPermissions = {
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

type UseProjectPermissionsOptions = {
  /**
   * Concrete project for row/detail update/delete checks.
   * When omitted, only `project:create` is evaluated (hub chrome);
   * update/delete stay safe-false until scoped per row.
   */
  resourceProject?: string
}

/**
 * Permission checks for project management actions.
 *
 * - `project:create` stays unscoped `can_i` (system grant; creating a project
 *   is not a project-scoped action).
 * - `project:update` / `project:delete` require a concrete `resourceProject`
 *   (never any-project for destructive UI).
 */
export function useProjectPermissions(options?: UseProjectPermissionsOptions): ProjectPermissions {
  const resourceProject = options?.resourceProject
  const hasProject = Boolean(resourceProject)

  return useCrudResourcePermissions({
    resourceType: 'project',
    tooltipTargets: {
      create: 'create a project',
      update: 'edit this project',
      delete: 'delete this project',
    },
    createCheck: { options: undefined },
    updateCheck: { options: { resourceProject, enabled: hasProject } },
    deleteCheck: { options: { resourceProject, enabled: hasProject } },
  })
}

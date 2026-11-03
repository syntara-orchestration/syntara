import { useCrudResourcePermissions } from '../../hooks/useCrudResourcePermissions'

type RolePermissions = {
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

type UseRolePermissionsOptions = {
  /**
   * When set, check role CRUD against this concrete project (name or UUID).
   * When omitted, checks are system-scoped (global Roles hub).
   */
  resourceProject?: string
}

/**
 * Permission checks for role management actions.
 *
 * Pass `resourceProject` on project detail screens so a grant in project A
 * does not enable create/edit/delete on project B. Omit it on the system
 * Roles hub (system-scoped `can_i` only).
 */
export function useRolePermissions(options?: UseRolePermissionsOptions): RolePermissions {
  const resourceProject = options?.resourceProject
  const scopedOptions = resourceProject ? { resourceProject } : undefined

  return useCrudResourcePermissions({
    resourceType: 'role',
    tooltipTargets: {
      create: 'create a role',
      update: 'edit this role',
      delete: 'delete this role',
    },
    createCheck: { options: scopedOptions },
    updateCheck: { options: scopedOptions },
    deleteCheck: { options: scopedOptions },
  })
}

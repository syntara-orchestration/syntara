/**
 * Shared types and helpers for permission checking.
 *
 * Used by `useCanI`, `usePermissionChecks`, nav filtering, and
 * the `DisabledWithTooltip` component.
 */

import { useCanI } from './useCanI'

export type PermissionRequirement = {
  action: string
  resourceType: string
}

/**
 * Generates a stable cache key for a permission check.
 * Format matches the policy naming convention: `resource_type:action`.
 */
export function permissionKey(check: PermissionRequirement): string {
  return `${check.resourceType}:${check.action}`
}

/**
 * Generates the standardized tooltip message for a disabled action.
 *
 * @param actionDescription - Human-readable description, e.g. "delete this workflow"
 * @param policyName - The policy identifier, e.g. "workflow:delete"
 */
export function permissionTooltip(actionDescription: string, policyName: string): string {
  return `To ${actionDescription}, you need a role with the ${policyName} policy. Contact your Admin to request access.`
}

/**
 * Generates the tooltip message shown when an action is blocked because the
 * selected project is the read-only built-in project.
 *
 * @param actionDescription - Human-readable description, e.g. "create a workflow"
 */
export function builtinProjectTooltip(actionDescription: string): string {
  return `Cannot ${actionDescription} in the built-in project. Select a different project first.`
}

export type ResourceCrudPermissions = {
  canCreate: boolean
  canUpdate: boolean
  canDelete: boolean
  isLoading: boolean
}

type PermissionScopeEntry = { project?: string; scope?: string }

export function isSystemScope(p: PermissionScopeEntry): boolean {
  return !p.project && (!p.scope || p.scope === 'system' || p.scope === 'any')
}

export function projectScopedNames(entries: PermissionScopeEntry[]): Set<string> {
  return new Set(entries.flatMap((p) => (p.scope === 'project' && p.project ? [p.project] : [])))
}

export function hasPermissionGrant(
  allPerms: { effect?: string; actions: string[]; scope?: string }[],
  actionKey: string
): boolean {
  return allPerms.some((p) => p.effect === 'allow' && p.actions.includes(actionKey) && p.scope === 'project')
}

/**
 * True when unscoped `can_i` allowed the action, or `what_can_i` lists a
 * project-scoped grant for the same `resourceType:action` key.
 *
 * Self-scoped grants are ignored by {@link hasPermissionGrant}.
 */
export function hasPermissionAnywhere(
  canIAllowed: boolean,
  allPerms: { effect?: string; actions: string[]; scope?: string }[],
  actionKey: string
): boolean {
  return canIAllowed || hasPermissionGrant(allPerms, actionKey)
}

/**
 * Shared hook for create/update/delete permission checks on a resource type.
 * All values default to `false` (safe-false) until the checks resolve.
 */
export function useResourceCrudPermissions(resourceType: string): ResourceCrudPermissions {
  const { allowed: canCreate, isChecking: isCheckingCreate } = useCanI('create', resourceType)
  const { allowed: canUpdate, isChecking: isCheckingUpdate } = useCanI('update', resourceType)
  const { allowed: canDelete, isChecking: isCheckingDelete } = useCanI('delete', resourceType)

  return {
    canCreate,
    canUpdate,
    canDelete,
    isLoading: isCheckingCreate || isCheckingUpdate || isCheckingDelete,
  }
}

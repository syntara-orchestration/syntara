import type { WorkflowAPI } from '@syntara/contracts'

type UserReference = WorkflowAPI.components['schemas']['UserReference']

/**
 * Audit fields (created_by / updated_by) return a UserReference ({ id, name }),
 * but some payloads still carry a plain id string — WorkflowVersionRead.created_by
 * is still a UUID, and older mock fixtures use strings.
 *
 * These helpers take `unknown` deliberately: they sit on an API boundary, so the
 * runtime shape is not guaranteed by the contract types alone.
 */
export function isUserReference(value: unknown): value is UserReference {
  if (typeof value !== 'object' || value === null) return false
  const { id, name } = value as { id?: unknown; name?: unknown }
  return typeof id === 'string' && typeof name === 'string'
}

/** Display name for an audit field, or undefined when there is nothing to show. */
export function userReferenceName(value: unknown): string | undefined {
  if (typeof value === 'string') return value.length > 0 ? value : undefined
  if (isUserReference(value) && value.name.length > 0) return value.name
  return undefined
}

/** User id for an audit field, or undefined when the value is not a UserReference. */
export function userReferenceId(value: unknown): string | undefined {
  return isUserReference(value) ? value.id : undefined
}

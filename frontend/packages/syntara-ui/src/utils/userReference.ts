import type { WorkflowAPI } from '@syntara/contracts'

type UserReference = WorkflowAPI.components['schemas']['UserReference']

/**
 * Audit fields (created_by / updated_by) return a UserReference ({ id, name }),
 * but some payloads may still carry a plain id string, and older mock fixtures
 * use strings.
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
export function toUserReferenceName(value: unknown): string | undefined {
  if (typeof value === 'string') return value.length > 0 ? value : undefined
  if (isUserReference(value) && value.name.length > 0) return value.name
  return undefined
}

/** User id for an audit field, or undefined when the value is not a UserReference. */
export function toUserReferenceId(value: unknown): string | undefined {
  return isUserReference(value) ? value.id : undefined
}

/**
 * Id to link to the user detail page, or undefined when there is no page to link to.
 *
 * created_by / updated_by point at a principal, which may be a service account,
 * an internal service, or a hard-deleted user. Only live `user` principals have a
 * detail page, so only those are linkable.
 */
export function toLinkedUserId(value: unknown): string | undefined {
  return isUserReference(value) && value.type === 'user' ? value.id : undefined
}

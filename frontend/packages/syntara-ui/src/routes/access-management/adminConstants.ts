import type { UsersAPI } from '@syntara/contracts'

type AuthType = UsersAPI.components['schemas']['AuthType']

/** User authentication type discriminator values from the backend AuthType enum. */
export const AUTH_TYPE_LOCAL = 'local' as const satisfies AuthType
export const AUTH_TYPE_FEDERATED = 'federated' as const satisfies AuthType

/** Auth source value for locally authenticated users (from the backend auth_sources array). */
export const AUTH_SOURCE_LOCAL = 'Local'

/** Name of the built-in administrators group as defined by the backend. */
export const BUILTIN_ADMINS_GROUP_NAME = 'admins'

/** Name of the built-in authenticated group as defined by the backend. */
export const BUILTIN_AUTHENTICATED_GROUP_NAME = 'authenticated'

/**
 * Excludes the built-in "authenticated" group from a list of groups. Every user is
 * implicitly a member of this group regardless of selection, so it should never appear
 * as a selectable option in group-assignment dropdowns (e.g. create user, group mapping).
 */
export function excludeAuthenticatedGroup<T extends { name: string }>(groups: readonly T[]): T[] {
  return groups.filter((g) => g.name !== BUILTIN_AUTHENTICATED_GROUP_NAME)
}

/** Explanation shown when the admin toggle is disabled for the built-in admin. */
export const BUILTIN_ADMIN_TOGGLE_DISABLED_REASON =
  'Only the built-in administrator can disable their own account, and only when at least one other enabled user exists in the admins group.'

/** Explanation shown when disabling any admin would leave no enabled admins. */
export const LAST_ADMIN_TOGGLE_DISABLED_REASON =
  'This user cannot be disabled because they are the last enabled user in the admins group.'

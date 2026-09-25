/**
 * Normalize a path template to TanStack Router `$param` syntax.
 *
 * Accepts AppRoute-style `:param` / `:param?` templates and leaves existing
 * `$param` templates unchanged so both catalogs compare as one URL contract.
 *
 * Example: `/users/:userId/groups/:groupId` → `/users/$userId/groups/$groupId`
 */
export function toTanStackPathTemplate(path: string): string {
  return path.replace(/:(\w+)\??/g, '$$$1')
}

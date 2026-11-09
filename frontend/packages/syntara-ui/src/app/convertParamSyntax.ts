/**
 * Normalize a path template to TanStack Router `$param` syntax.
 *
 * Accepts colon-style `:param` / `:param?` templates and leaves existing
 * `$param` templates unchanged.
 *
 * Example: `/users/:userId/groups/:groupId` → `/users/$userId/groups/$groupId`
 */
export function toTanStackPathTemplate(path: string): string {
  return path.replace(/:(\w+)\??/g, '$$$1')
}

/**
 * Safely extracts the `sub` (subject / user ID) claim from a JWT access token.
 * Returns `null` if the token is malformed or the claim is missing.
 */
export function getUserIdFromToken(token: string | null | undefined): string | null {
  if (!token) return null
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    // JWT payloads use base64url encoding; convert to standard base64 for atob
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    // atob requires padding to a multiple of 4 characters
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=')
    const payload: unknown = JSON.parse(atob(padded))
    if (typeof payload === 'object' && payload !== null && 'sub' in payload) {
      const { sub } = payload
      return typeof sub === 'string' ? sub : null
    }
    return null
  } catch {
    return null
  }
}

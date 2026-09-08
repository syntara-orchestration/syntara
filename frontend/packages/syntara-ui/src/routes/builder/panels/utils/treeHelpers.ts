/**
 * Builds a DOM-safe id for a TreeView node from arbitrary path segments (e.g. execution
 * data keys, which can contain spaces, punctuation, or other characters that need CSS
 * escaping when used in a selector). Encoding out every non-alphanumeric character avoids
 * that escaping entirely, rather than relying on consumers (e.g. axe-core's selector
 * generation) to escape correctly. Hyphens are encoded too so the '-' used to join segments
 * stays unambiguous — otherwise ['a-b'] and ['a', 'b'] would produce the same id.
 */
export function toTreeItemId(pathSegments: string[]): string {
  return [
    'node',
    ...pathSegments.map((segment) =>
      segment.replace(/[^a-zA-Z0-9_]/g, (char) => `_${char.codePointAt(0)?.toString(16)}_`)
    ),
  ].join('-')
}

export function isExpandable(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function isUrlValue(value: unknown): value is string {
  if (typeof value !== 'string') return false
  return (value.startsWith('https://') && value.length > 8) || (value.startsWith('http://') && value.length > 7)
}

export function formatLeafValue(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number') return String(value)
  if (typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return JSON.stringify(value)
  return String(value)
}

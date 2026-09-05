import { toTanStackPathTemplate } from '../../src/app/convertParamSyntax'

import { plainObjectSchema } from './route-manifest-schema'

/**
 * Convert a path template to TanStack `$param` syntax.
 *
 * Accepts AppRoute-style `:param` and TanStack `$param` forms so AppRoute
 * helpers and router definitions compare as the same URL contract.
 *
 * @param path - Raw path template from any route source
 * @returns Canonical template using `$param` placeholders
 */
export function normalizeTemplate(path: string): string {
  return toTanStackPathTemplate(path)
}

/**
 * Read ordered parameter names from a canonical `$param` template.
 *
 * @param template - Canonical path template
 * @returns Parameter names in path order (empty for static routes)
 */
export function extractParameters(template: string): string[] {
  const params: string[] = []
  for (const match of template.matchAll(/\$([A-Za-z_][\w]*)/g)) {
    const name = match[1]
    if (name) params.push(name)
  }
  return params
}

/**
 * Serialize a value to JSON with sorted object keys and a trailing newline.
 *
 * Keeps committed manifest files stable across machines and Node versions.
 *
 * @param value - Any JSON-serializable value
 * @returns Pretty-printed JSON ending with `\n`
 */
export function stableStringify(value: unknown): string {
  return `${JSON.stringify(value, replacer, 2)}\n`
}

/**
 * JSON.stringify replacer that sorts plain-object keys.
 *
 * @param _key - Property name (unused)
 * @param value - Property value
 * @returns Value with object keys sorted when applicable
 */
function replacer(_key: string, value: unknown): unknown {
  const parsed = plainObjectSchema.safeParse(value)
  if (!parsed.success) return value

  const sorted: Record<string, unknown> = {}
  for (const key of Object.keys(parsed.data).sort()) {
    sorted[key] = parsed.data[key]
  }
  return sorted
}

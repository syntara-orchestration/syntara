import { stableStringify } from './normalize-route'
import { normalizedRouteSchema, type NormalizedRoute, type RouteManifest } from './route-manifest-schema'

/**
 * Structured difference between two route manifests.
 */
export type RouteManifestDiff = {
  /** Templates present only in the newer manifest. */
  added: string[]
  /** Templates present only in the older manifest. */
  removed: string[]
  /** Templates present in both manifests but with different fields. */
  changed: Array<{ template: string; before: NormalizedRoute; after: NormalizedRoute }>
}

/**
 * Compare two manifests by template and classify additions, removals, and changes.
 *
 * @param before - Previously committed (or older) manifest
 * @param after - Freshly generated (or newer) manifest
 * @returns Sorted diff suitable for CI logs and test failures
 */
export function diffRouteManifest(before: RouteManifest, after: RouteManifest): RouteManifestDiff {
  const beforeByTemplate = new Map(before.routes.map((route) => [route.template, route]))
  const afterByTemplate = new Map(after.routes.map((route) => [route.template, route]))

  const added: string[] = []
  const removed: string[] = []
  const changed: RouteManifestDiff['changed'] = []

  for (const template of afterByTemplate.keys()) {
    if (!beforeByTemplate.has(template)) {
      added.push(template)
    }
  }

  for (const template of beforeByTemplate.keys()) {
    if (!afterByTemplate.has(template)) {
      removed.push(template)
    }
  }

  for (const [template, afterRoute] of afterByTemplate) {
    const beforeRoute = beforeByTemplate.get(template)
    if (!beforeRoute) continue
    if (!routesEqual(beforeRoute, afterRoute)) {
      changed.push({ template, before: beforeRoute, after: afterRoute })
    }
  }

  added.sort()
  removed.sort()
  changed.sort((a, b) => a.template.localeCompare(b.template))

  return { added, removed, changed }
}

/**
 * Compare two normalized routes via the Zod schema + stable JSON.
 *
 * Field-by-field hand checks drift when the schema grows; this stays aligned.
 *
 * @param a - Left route
 * @param b - Right route
 * @returns `true` when the schema-shaped payloads match
 */
function routesEqual(a: NormalizedRoute, b: NormalizedRoute): boolean {
  return stableStringify(normalizedRouteSchema.parse(a)) === stableStringify(normalizedRouteSchema.parse(b))
}

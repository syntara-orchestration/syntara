import { extractParameters, normalizeTemplate } from './normalize-route'
import { collectExportedRoutePaths, collectRouteGraph, parseRouteSource } from './route-graph'
import { absolutePathSchema, type NormalizedRoute, type ParsedCreateRoute } from './route-manifest-schema'

/**
 * Extract the interior of a `{ ... }` object starting at `openBraceIndex`,
 * respecting nested braces and string literals.
 *
 * @param source - Full source text
 * @param openBraceIndex - Index of the opening `{`
 * @returns Object body without the outer braces, or `null` if unbalanced
 */
export function extractBalancedObjectBody(source: string, openBraceIndex: number): string | null {
  if (source[openBraceIndex] !== '{') return null

  let depth = 0
  let inString: '"' | "'" | '`' | null = null
  let escaped = false

  for (let i = openBraceIndex; i < source.length; i++) {
    const ch = source[i]
    if (!ch) continue

    if (inString) {
      if (escaped) {
        escaped = false
        continue
      }
      if (ch === '\\') {
        escaped = true
        continue
      }
      if (ch === inString) inString = null
      continue
    }

    if (ch === '"' || ch === "'" || ch === '`') {
      inString = ch
      continue
    }

    if (ch === '{') {
      depth += 1
      continue
    }

    if (ch === '}') {
      depth -= 1
      if (depth === 0) return source.slice(openBraceIndex + 1, i)
    }
  }

  return null
}

/**
 * Options for {@link parseCreateRouteBlocks}.
 */
export type ParseCreateRouteBlocksOptions = {
  routeReferencePaths?: Record<string, string>
}

/**
 * Parse `createRoute({ ... })` blocks from a route module source string.
 *
 * Uses the TypeScript parser and symbol resolution for parent references.
 * Source analysis avoids executing page components or CSS.
 *
 * Redirect targets may be string literals or exported route references.
 *
 * @param source - TypeScript/TSX file contents
 * @param options - Optional route references for non-literal redirects
 * @returns Raw path entries with kind and optional redirect target
 */
export function parseCreateRouteBlocks(
  source: string,
  options: ParseCreateRouteBlocksOptions = {}
): ParsedCreateRoute[] {
  return parseRouteSource(source, (body) => extractRedirectTarget(body, options.routeReferencePaths))
}

/**
 * Read `redirect({ to: ... })` from a createRoute options body.
 *
 * Supports string literals and route-reference expressions. Other expression
 * shapes throw so redirect metadata is never silently dropped.
 *
 * @param body - Interior of a createRoute options object
 * @param routeReferencePaths - Exported route paths for resolving references
 * @returns Absolute redirect path, or `undefined` when no redirect is present
 */
function extractRedirectTarget(body: string, routeReferencePaths?: Record<string, string>): string | undefined {
  const literalMatch = body.match(/\bredirect\(\{\s*to:\s*['"]([^'"]+)['"]/)
  if (literalMatch?.[1]) return literalMatch[1]

  const routeRef = body.match(/\bredirect\(\{\s*to:\s*routeRefs\.(\w+)\.fullPath/)
  if (routeRef?.[1]) {
    const resolved = absolutePathSchema.safeParse(routeReferencePaths?.[routeRef[1]])
    if (!resolved.success) throw new Error(`Could not resolve routeRefs.${routeRef[1]}.fullPath in redirect`)
    return resolved.data
  }

  const otherMatch = body.match(/\bredirect\(\{\s*to:\s*([^,\s}'"]+)/)
  if (otherMatch?.[1]) {
    throw new Error(`Unsupported redirect({ to: ${otherMatch[1]} }) — use a string literal or route reference`)
  }

  return undefined
}

/**
 * Collect normalized routes from route modules mounted in the TanStack tree.
 *
 * Follows mounted route arrays and addChildren calls through TypeScript symbols,
 * including imports and re-exports. Unmounted declarations do not enter the baseline.
 *
 * @param routesDir - Absolute path to `src/app/routes`
 * @param treeSource - Contents of `tanstackRouteTree.tsx`
 * @param routeReferencePaths - Exported route paths for resolving redirect targets
 * @returns Deduplicated router routes plus unmounted paths relative to routesDir
 */
export function collectMountedRouterRoutes(
  routesDir: string,
  treeSource: string,
  routeReferencePaths?: Record<string, string>
): { routes: NormalizedRoute[]; unmountedRouteFiles: string[] } {
  const { routes, unmountedRouteFiles } = collectRouteGraph(routesDir, treeSource, (body) =>
    extractRedirectTarget(body, routeReferencePaths)
  )

  const byTemplate = new Map<string, NormalizedRoute>()

  for (const route of routes) {
    mergeRoute(byTemplate, {
      template: normalizeTemplate(route.path),
      parameters: extractParameters(normalizeTemplate(route.path)),
      kind: route.kind,
      sources: ['router'],
      ...(route.redirectTo ? { redirectTo: normalizeTemplate(route.redirectTo) } : {}),
    })
  }

  return { routes: [...byTemplate.values()], unmountedRouteFiles }
}

/** Resolve exported route objects from the route-reference barrel. */
export function collectRouteReferencePaths(routesDir: string, treeSource: string, referenceFile: string) {
  return collectExportedRoutePaths(routesDir, treeSource, referenceFile)
}

/**
 * Collect navigation paths from `navigationItems.tsx` source without importing JSX.
 *
 * Resolves every `routeRefs.foo.fullPath` use against the route objects exported
 * from the route-reference barrel. This covers destinations and matching metadata;
 * group identity strings have no route reference and are skipped.
 *
 * @param navigationSource - File contents of `navigationItems.tsx`
 * @param routeReferencePaths - Exported route paths used to resolve references
 * @returns Sorted unique templates
 */
export function collectNavigationPathsFromSource(
  navigationSource: string,
  routeReferencePaths: Record<string, string>
): string[] {
  const paths = new Set<string>()

  for (const match of navigationSource.matchAll(/\brouteRefs\.(\w+)\.fullPath/g)) {
    const name = match[1]
    if (!name) continue
    const resolved = absolutePathSchema.safeParse(routeReferencePaths[name])
    if (!resolved.success) {
      const line = navigationSource.slice(0, match.index).split('\n').length
      throw new Error(`Could not resolve routeRefs.${name}.fullPath in navigationItems.tsx:${line}`)
    }
    paths.add(normalizeTemplate(resolved.data))
  }

  return [...paths].sort()
}

/**
 * Collect bookmarkable paths handled in `App.tsx` before `RouterProvider`.
 *
 * Reads the callback path constant when App routes the callback before RouterProvider.
 *
 * @param appSource - File contents of `App.tsx`
 * @param appLevelPathSource - Source for the app-level callback path constant
 * @returns Normalized app-level route entries
 */
export function collectAppLevelRoutesFromSource(appSource: string, appLevelPathSource: string): NormalizedRoute[] {
  const byTemplate = new Map<string, NormalizedRoute>()

  if (appSource.includes('location.pathname === testSignInCallbackPath')) {
    const match = appLevelPathSource.match(/export\s+const\s+testSignInCallbackPath\s*=\s*['"](\/[^'"]+)['"]/)
    const path = absolutePathSchema.safeParse(match?.[1])
    if (path.success) {
      const template = normalizeTemplate(path.data)
      byTemplate.set(template, {
        template,
        parameters: extractParameters(template),
        kind: 'app',
        sources: ['app'],
      })
    }
  }

  return [...byTemplate.values()]
}

/**
 * Collect the catch-all fallback from `__root.ts` not-found navigation.
 *
 * @param rootSource - File contents of `src/app/routes/__root.ts`
 * @returns Normalized fallback route entry
 * @throws If no `navigate({ to: '...' })` target is found
 */
export function collectFallbackRouteFromSource(rootSource: string): NormalizedRoute {
  const match = rootSource.match(/\bnavigate\(\{\s*to:\s*['"]([^'"]+)['"]/)
  const redirectTo = absolutePathSchema.safeParse(match?.[1])
  if (!redirectTo.success) {
    throw new Error('Could not find not-found navigate({ to }) target in __root.ts')
  }

  return {
    template: '*',
    parameters: [],
    kind: 'fallback',
    redirectTo: normalizeTemplate(redirectTo.data),
    sources: ['router'],
  }
}

/**
 * Merge a route into a template map, combining sources and preferring redirects.
 *
 * @param byTemplate - Mutable map keyed by canonical template
 * @param entry - Route entry to merge
 */
function mergeRoute(byTemplate: Map<string, NormalizedRoute>, entry: NormalizedRoute): void {
  const existing = byTemplate.get(entry.template)
  if (existing) {
    existing.sources = uniqueSources([...existing.sources, ...entry.sources])
    if (entry.kind === 'redirect') {
      existing.kind = 'redirect'
      existing.redirectTo = entry.redirectTo
    }
    return
  }
  byTemplate.set(entry.template, entry)
}

/**
 * Deduplicate source tags while preserving type information.
 *
 * @param sources - Source tags that may contain duplicates
 * @returns Unique source tags
 */
function uniqueSources(sources: NormalizedRoute['sources']): NormalizedRoute['sources'] {
  return [...new Set(sources)]
}

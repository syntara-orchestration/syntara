import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import { extractParameters, normalizeTemplate } from './normalize-route'
import type { NormalizedRoute, RouteKind } from './types'

const PATH_LITERAL = /['"](\/[^'"]*)['"]/g

type ParsedCreateRoute = {
  path: string
  kind: RouteKind
  redirectTo?: string
}

type NavItemLike = { path: string; children?: NavItemLike[] }

/**
 * Walk a nested catalog (such as `AppRoute`) and collect string path values.
 *
 * @param value - Nested object or string path
 * @param out - Mutable set used while recursing
 * @returns The same set for chaining
 */
export function collectPathsFromObject(value: unknown, out: Set<string> = new Set()): Set<string> {
  if (typeof value === 'string' && value.startsWith('/')) {
    out.add(value)
    return out
  }
  if (value && typeof value === 'object') {
    for (const child of Object.values(value as Record<string, unknown>)) {
      collectPathsFromObject(child, out)
    }
  }
  return out
}

/**
 * Parse `createRoute({ ... })` blocks from a route module source string.
 *
 * Uses text parsing so collectors never import page components or CSS.
 *
 * @param source - TypeScript/TSX file contents
 * @returns Raw path entries with kind and optional redirect target
 */
export function parseCreateRouteBlocks(source: string): ParsedCreateRoute[] {
  const results: ParsedCreateRoute[] = []
  const blockRegex = /createRoute\(\{([\s\S]*?)\n\s*\}\)/g

  for (const match of source.matchAll(blockRegex)) {
    const body = match[1]
    if (!body) continue

    const pathMatch = body.match(/\bpath:\s*['"]([^'"]+)['"]/)
    const path = pathMatch?.[1]
    if (!path) continue

    const redirectMatch = body.match(/\bredirect\(\{\s*to:\s*['"]([^'"]+)['"]/)
    const redirectTo = redirectMatch?.[1]
    if (redirectTo) {
      results.push({ path, kind: 'redirect', redirectTo })
      continue
    }

    results.push({ path, kind: 'page' })
  }

  return results
}

/**
 * Collect normalized routes from every non-test `*.tsx` file in a routes directory.
 *
 * @param routesDir - Absolute path to `src/app/routes`
 * @returns Deduplicated router routes (not yet sorted)
 */
export function collectRouterRoutes(routesDir: string): NormalizedRoute[] {
  const files = readdirSync(routesDir).filter((name) => name.endsWith('.tsx') && !name.includes('.test.'))
  const byTemplate = new Map<string, NormalizedRoute>()

  for (const file of files) {
    const source = readFileSync(join(routesDir, file), 'utf-8')
    for (const route of parseCreateRouteBlocks(source)) {
      const template = normalizeTemplate(route.path)
      const entry: NormalizedRoute = {
        template,
        parameters: extractParameters(template),
        kind: route.kind,
        sources: ['router'],
        ...(route.redirectTo ? { redirectTo: normalizeTemplate(route.redirectTo) } : {}),
      }
      const existing = byTemplate.get(template)
      if (existing) {
        existing.sources = uniqueSources([...existing.sources, ...entry.sources])
        if (entry.kind === 'redirect') {
          existing.kind = 'redirect'
          existing.redirectTo = entry.redirectTo
        }
      } else {
        byTemplate.set(template, entry)
      }
    }
  }

  return [...byTemplate.values()]
}

/**
 * Collect canonical path templates from `AppRoute.tsx` source text.
 *
 * @param appRouteSource - File contents of `AppRoute.tsx`
 * @returns Sorted unique templates
 */
export function collectAppRoutePaths(appRouteSource: string): string[] {
  const paths = new Set<string>()
  for (const match of appRouteSource.matchAll(PATH_LITERAL)) {
    const path = match[1]
    if (path) paths.add(normalizeTemplate(path))
  }
  return [...paths].sort()
}

/**
 * Collect path templates from an in-memory navigation tree.
 *
 * @param items - Navigation items with `path` and optional `children`
 * @returns Sorted unique templates
 */
export function collectNavigationPaths(items: NavItemLike[]): string[] {
  const paths = new Set<string>()

  const walk = (nodes: NavItemLike[]) => {
    for (const node of nodes) {
      paths.add(normalizeTemplate(node.path))
      if (node.children?.length) walk(node.children)
    }
  }

  walk(items)
  return [...paths].sort()
}

/**
 * Collect navigation paths from `navigationItems.tsx` source without importing JSX.
 *
 * Resolves `path: AppRoute.Foo.Bar` against the live `AppRoute` object and also
 * accepts literal `path: '/...'` strings.
 *
 * @param navigationSource - File contents of `navigationItems.tsx`
 * @param appRouteCatalog - The `AppRoute` object used to resolve references
 * @returns Sorted unique templates
 */
export function collectNavigationPathsFromSource(
  navigationSource: string,
  appRouteCatalog: unknown
): string[] {
  const paths = new Set<string>()

  for (const match of navigationSource.matchAll(/\bpath:\s*(AppRoute(?:\.\w+)+)/g)) {
    const expression = match[1]
    if (!expression) continue
    const resolved = resolveAppRouteReference(appRouteCatalog, expression)
    if (typeof resolved === 'string') {
      paths.add(normalizeTemplate(resolved))
    }
  }

  for (const match of navigationSource.matchAll(/\bpath:\s*['"](\/[^'"]+)['"]/g)) {
    const path = match[1]
    if (path) paths.add(normalizeTemplate(path))
  }

  return [...paths].sort()
}

/**
 * Resolve a dotted `AppRoute.AccessManagement.Users` expression to its value.
 *
 * @param appRouteCatalog - Root `AppRoute` object
 * @param expression - Full expression including the `AppRoute` prefix
 * @returns The resolved value, or `undefined` when the path does not exist
 */
export function resolveAppRouteReference(appRouteCatalog: unknown, expression: string): unknown {
  const parts = expression.split('.')
  if (parts[0] !== 'AppRoute') return undefined
  let current: unknown = appRouteCatalog
  for (const part of parts.slice(1)) {
    if (!current || typeof current !== 'object') return undefined
    current = (current as Record<string, unknown>)[part]
  }
  return current
}

/**
 * Return fixed app-level routes that are bookmarkable but outside TanStack Router.
 *
 * @returns Normalized app-level route entries
 */
export function collectAppLevelRoutes(): NormalizedRoute[] {
  return [
    {
      template: '/auth/test-signin-callback',
      parameters: [],
      kind: 'app',
      sources: ['app', 'appRoute'],
    },
  ]
}

/**
 * Return the catch-all fallback recorded from the root route not-found behavior.
 *
 * @returns Normalized fallback route entry
 */
export function collectFallbackRoute(): NormalizedRoute {
  return {
    template: '*',
    parameters: [],
    kind: 'fallback',
    redirectTo: '/workflows',
    sources: ['router'],
  }
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

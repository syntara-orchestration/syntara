import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { basename, join } from 'node:path'

import { extractParameters, normalizeTemplate } from './normalize-route'
import {
  absolutePathSchema,
  parsedCreateRouteSchema,
  plainObjectSchema,
  type NormalizedRoute,
  type ParsedCreateRoute,
} from './route-manifest-schema'

const PATH_LITERAL = /['"](\/[^'"]*)['"]/g

type NavItemLike = { path: string; children?: NavItemLike[] }

/**
 * Walk a nested catalog (such as `AppRoute`) and collect string path values.
 *
 * @param value - Nested object or string path
 * @param out - Mutable set used while recursing
 * @returns The same set for chaining
 */
export function collectPathsFromObject(value: unknown, out: Set<string> = new Set()): Set<string> {
  const path = absolutePathSchema.safeParse(value)
  if (path.success) {
    out.add(path.data)
    return out
  }
  const object = plainObjectSchema.safeParse(value)
  if (object.success) {
    for (const child of Object.values(object.data)) {
      collectPathsFromObject(child, out)
    }
  }
  return out
}

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
 * Parse `createRoute({ ... })` blocks from a route module source string.
 *
 * Uses brace-depth scanning so nested option objects cannot truncate the block.
 * Text parsing avoids importing page components or CSS.
 *
 * @param source - TypeScript/TSX file contents
 * @returns Raw path entries with kind and optional redirect target
 */
export function parseCreateRouteBlocks(source: string): ParsedCreateRoute[] {
  const results: ParsedCreateRoute[] = []
  const startRegex = /createRoute\s*\(\s*\{/g

  for (const match of source.matchAll(startRegex)) {
    const openBraceIndex = (match.index ?? 0) + match[0].lastIndexOf('{')
    const body = extractBalancedObjectBody(source, openBraceIndex)
    if (body === null) continue

    const pathMatch = body.match(/\bpath:\s*['"]([^'"]+)['"]/)
    const path = pathMatch?.[1]
    if (!path) continue

    const redirectMatch = body.match(/\bredirect\(\{\s*to:\s*['"]([^'"]+)['"]/)
    const redirectTo = redirectMatch?.[1]
    const parsed = parsedCreateRouteSchema.safeParse(
      redirectTo ? { path, kind: 'redirect', redirectTo } : { path, kind: 'page' }
    )
    if (parsed.success) results.push(parsed.data)
  }

  return results
}

/**
 * Parse `tanstackRouteTree.tsx` for route modules that are imported and mounted.
 *
 * A module counts as mounted only when its export is both imported from
 * `./routes/...` and spread into `addChildren([...])`.
 *
 * @param treeSource - File contents of `tanstackRouteTree.tsx`
 * @returns Sorted unique route module basenames (for example `workflows`)
 */
export function parseMountedRouteModules(treeSource: string): string[] {
  const importByBinding = new Map<string, string>()

  for (const match of treeSource.matchAll(/import\s*\{\s*(\w+)\s*\}\s*from\s*['"]\.\/routes\/([^'"]+)['"]/g)) {
    const binding = match[1]
    const modulePath = match[2]
    if (!binding || !modulePath) continue
    importByBinding.set(binding, basename(modulePath))
  }

  const mounted = new Set<string>()
  const childrenMatch = treeSource.match(/addChildren\(\[([\s\S]*?)\]\)/)
  const childrenBody = childrenMatch?.[1] ?? ''

  for (const match of childrenBody.matchAll(/\.\.\.(\w+)/g)) {
    const binding = match[1]
    if (!binding) continue
    const moduleName = importByBinding.get(binding)
    if (moduleName) mounted.add(moduleName)
  }

  return [...mounted].sort()
}

/**
 * Collect normalized routes from route modules mounted in the TanStack tree.
 *
 * Only files referenced by `tanstackRouteTree.tsx` are scraped, so orphan
 * `createRoute` modules cannot pollute the baseline.
 *
 * @param routesDir - Absolute path to `src/app/routes`
 * @param treeSource - Contents of `tanstackRouteTree.tsx`
 * @returns Deduplicated router routes plus any unmounted route file basenames
 */
export function collectMountedRouterRoutes(
  routesDir: string,
  treeSource: string
): { routes: NormalizedRoute[]; unmountedRouteFiles: string[] } {
  const mountedModules = new Set(parseMountedRouteModules(treeSource))
  const routeFiles = readdirSync(routesDir).filter(
    (name) => (name.endsWith('.tsx') || name.endsWith('.ts')) && !name.includes('.test.') && name !== '__root.ts'
  )

  const unmountedRouteFiles = routeFiles
    .filter((name) => {
      const base = basename(name, name.endsWith('.tsx') ? '.tsx' : '.ts')
      if (base === '__root') return false
      const source = readFileSync(join(routesDir, name), 'utf-8')
      return parseCreateRouteBlocks(source).length > 0 && !mountedModules.has(base)
    })
    .sort()

  const byTemplate = new Map<string, NormalizedRoute>()

  for (const moduleName of mountedModules) {
    const fileName = resolveRouteModuleFile(routesDir, moduleName)
    if (!fileName) continue
    const source = readFileSync(join(routesDir, fileName), 'utf-8')
    for (const route of parseCreateRouteBlocks(source)) {
      mergeRoute(byTemplate, {
        template: normalizeTemplate(route.path),
        parameters: extractParameters(normalizeTemplate(route.path)),
        kind: route.kind,
        sources: ['router'],
        ...(route.redirectTo ? { redirectTo: normalizeTemplate(route.redirectTo) } : {}),
      })
    }
  }

  return { routes: [...byTemplate.values()], unmountedRouteFiles }
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
    const path = absolutePathSchema.safeParse(match[1])
    if (path.success) paths.add(normalizeTemplate(path.data))
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
export function collectNavigationPathsFromSource(navigationSource: string, appRouteCatalog: unknown): string[] {
  const paths = new Set<string>()

  for (const match of navigationSource.matchAll(/\bpath:\s*(AppRoute(?:\.\w+)+)/g)) {
    const expression = match[1]
    if (!expression) continue
    const resolved = absolutePathSchema.safeParse(resolveAppRouteReference(appRouteCatalog, expression))
    if (resolved.success) paths.add(normalizeTemplate(resolved.data))
  }

  for (const match of navigationSource.matchAll(/\bpath:\s*['"](\/[^'"]+)['"]/g)) {
    const path = absolutePathSchema.safeParse(match[1])
    if (path.success) paths.add(normalizeTemplate(path.data))
  }

  return [...paths].sort()
}

/**
 * Parse `export const AppRoute = { ... }` from source into a nested catalog.
 *
 * Avoids importing `AppRoute.tsx` from Node/tsconfig.node (no JSX).
 *
 * @param source - File contents of `AppRoute.tsx`
 * @returns Nested catalog of path strings
 */
export function parseAppRouteCatalog(source: string): Record<string, unknown> {
  const match = /export\s+const\s+AppRoute\s*=\s*\{/.exec(source)
  if (!match || match.index === undefined) {
    throw new Error('Could not find export const AppRoute = { in AppRoute source')
  }

  const openBraceIndex = match.index + match[0].lastIndexOf('{')
  const body = extractBalancedObjectBody(source, openBraceIndex)
  if (body === null) {
    throw new Error('Unbalanced AppRoute object literal')
  }

  return parseObjectLiteral(body)
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
    const object = plainObjectSchema.safeParse(current)
    if (!object.success) return undefined
    current = object.data[part]
  }
  return current
}

/**
 * Parse a nested object-literal body of string and object properties.
 *
 * @param body - Object interior without outer braces
 * @returns Nested record of string path values
 */
function parseObjectLiteral(body: string): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  let i = 0

  while (i < body.length) {
    while (i < body.length && /[\s,]/.test(body[i] ?? '')) i += 1
    if (i >= body.length) break

    const keyMatch = /^([A-Za-z_]\w*)\s*:/.exec(body.slice(i))
    if (!keyMatch?.[1]) break
    const key = keyMatch[1]
    i += keyMatch[0].length

    while (i < body.length && /\s/.test(body[i] ?? '')) i += 1

    if (body[i] === '{') {
      const nestedBody = extractBalancedObjectBody(body, i)
      if (nestedBody === null) {
        throw new Error(`Unbalanced nested object at key ${key}`)
      }
      result[key] = parseObjectLiteral(nestedBody)
      i += nestedBody.length + 2
      continue
    }

    const stringMatch = /^(['"])((?:\\.|(?!\1).)*)\1/.exec(body.slice(i))
    if (!stringMatch?.[2]) {
      throw new Error(`Expected string or object value at key ${key}`)
    }
    result[key] = stringMatch[2].replace(/\\(['"\\])/g, '$1')
    i += stringMatch[0].length
  }

  return result
}

/**
 * Collect bookmarkable paths handled in `App.tsx` before `RouterProvider`.
 *
 * Parses `location.pathname === AppRoute...` and literal pathname comparisons
 * so changing the escape hatch updates the baseline.
 *
 * @param appSource - File contents of `App.tsx`
 * @param appRouteCatalog - Live `AppRoute` object for resolving references
 * @returns Normalized app-level route entries
 */
export function collectAppLevelRoutesFromSource(appSource: string, appRouteCatalog: unknown): NormalizedRoute[] {
  const byTemplate = new Map<string, NormalizedRoute>()

  for (const match of appSource.matchAll(/location\.pathname\s*===\s*(AppRoute(?:\.\w+)+)/g)) {
    const expression = match[1]
    if (!expression) continue
    const resolved = absolutePathSchema.safeParse(resolveAppRouteReference(appRouteCatalog, expression))
    if (!resolved.success) continue
    const template = normalizeTemplate(resolved.data)
    byTemplate.set(template, {
      template,
      parameters: extractParameters(template),
      kind: 'app',
      sources: ['app', 'appRoute'],
    })
  }

  for (const match of appSource.matchAll(/location\.pathname\s*===\s*['"](\/[^'"]+)['"]/g)) {
    const path = absolutePathSchema.safeParse(match[1])
    if (!path.success) continue
    const template = normalizeTemplate(path.data)
    byTemplate.set(template, {
      template,
      parameters: extractParameters(template),
      kind: 'app',
      sources: ['app'],
    })
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
 * Resolve a mounted module basename to a file under `routesDir`.
 *
 * @param routesDir - Absolute path to `src/app/routes`
 * @param moduleName - Basename without extension (for example `workflows`)
 * @returns Matching filename, or `undefined` when missing
 */
function resolveRouteModuleFile(routesDir: string, moduleName: string): string | undefined {
  const candidates = [`${moduleName}.tsx`, `${moduleName}.ts`]
  for (const candidate of candidates) {
    if (existsSync(join(routesDir, candidate))) return candidate
  }
  return undefined
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

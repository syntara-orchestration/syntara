import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import {
  collectAppLevelRoutesFromSource,
  collectAppRoutePaths,
  collectFallbackRouteFromSource,
  collectMountedRouterRoutes,
  collectNavigationPathsFromSource,
  parseAppRouteCatalog,
} from './collect-routes'
import {
  ROUTE_MANIFEST_COMMENT_KEY,
  ROUTE_MANIFEST_NOTICE,
  routeManifestSchema,
  type NormalizedRoute,
  type RouteManifest,
} from './route-manifest-schema'

/**
 * Result of building a manifest plus source-parity findings.
 */
export type ManifestBuildResult = {
  /** Normalized route contract built from mounted router, app, and fallback entries. */
  manifest: RouteManifest
  /** AppRoute templates missing from the manifest after known exceptions. */
  appRouteOnly: string[]
  /** Navigation templates missing from the manifest after known exceptions. */
  navigationOnly: string[]
  /** Route modules that define `createRoute` but are not mounted in the tree. */
  unmountedRouteFiles: string[]
}

/**
 * AppRoute / navigation templates intentionally absent from the router tree.
 *
 * Keep each entry documented. Growing this set without review hides parity drift.
 * Paths already present in the manifest (including `kind: "app"`) do not belong here.
 */
export const SOURCE_PARITY_EXCEPTIONS = new Set([
  // Declared in AppRoute but unused; not a live browser route.
  '/dashboard',
  // Placeholder support links — no createRoute yet.
  '/support/documentation',
  '/support/faq',
  // Nav section root; children are real routes.
  '/system-administration',
])

/**
 * Options for {@link buildRouteManifest}.
 */
export type BuildRouteManifestOptions = {
  /** Absolute path to the `packages/syntara-ui` package root (or a fixture root). */
  pkgRoot: string
}

/**
 * Build the normalized route manifest from live package sources.
 *
 * Reads the mounted TanStack tree, App.tsx escape hatches, `__root` fallback,
 * AppRoute, and navigation sources under `pkgRoot`.
 *
 * @param options - Package root used to locate source files
 * @returns Manifest plus any source-parity gaps
 */
export function buildRouteManifest(options: BuildRouteManifestOptions): ManifestBuildResult {
  const { pkgRoot } = options
  const routesDir = join(pkgRoot, 'src/app/routes')
  const appRouteSource = readFileSync(join(pkgRoot, 'src/app/AppRoute.tsx'), 'utf-8')
  const navigationSource = readFileSync(join(pkgRoot, 'src/app/navigationItems.tsx'), 'utf-8')
  const appSource = readFileSync(join(pkgRoot, 'src/app/App.tsx'), 'utf-8')
  const rootSource = readFileSync(join(pkgRoot, 'src/app/routes/__root.ts'), 'utf-8')
  const treeSource = readFileSync(join(pkgRoot, 'src/app/tanstackRouteTree.tsx'), 'utf-8')

  const appRouteCatalog = parseAppRouteCatalog(appRouteSource)
  const { routes: routerRoutes, unmountedRouteFiles } = collectMountedRouterRoutes(
    routesDir,
    treeSource,
    appRouteCatalog
  )
  const appLevel = collectAppLevelRoutesFromSource(appSource, appRouteCatalog)
  const fallback = collectFallbackRouteFromSource(rootSource)

  const byTemplate = new Map<string, NormalizedRoute>()
  for (const route of [...routerRoutes, ...appLevel, fallback]) {
    byTemplate.set(route.template, sortRouteFields(route))
  }

  const routes = [...byTemplate.values()].sort((a, b) => a.template.localeCompare(b.template))
  const manifestTemplates = new Set(routes.map((r) => r.template))

  const appRoutePaths = collectAppRoutePaths(appRouteSource)
  const navigationPaths = collectNavigationPathsFromSource(navigationSource, appRouteCatalog)

  const appRouteOnly = appRoutePaths.filter(
    (template) => !manifestTemplates.has(template) && !SOURCE_PARITY_EXCEPTIONS.has(template)
  )
  const navigationOnly = navigationPaths.filter(
    (template) => !manifestTemplates.has(template) && !SOURCE_PARITY_EXCEPTIONS.has(template)
  )

  // Annotate sources when AppRoute / nav also declare the same template.
  for (const route of routes) {
    if (appRoutePaths.includes(route.template) && !route.sources.includes('appRoute')) {
      route.sources = [...route.sources, 'appRoute']
    }
    if (navigationPaths.includes(route.template) && !route.sources.includes('navigation')) {
      route.sources = [...route.sources, 'navigation']
    }
    route.sources = sortedSources([...new Set(route.sources)])
  }

  return {
    manifest: routeManifestSchema.parse({
      [ROUTE_MANIFEST_COMMENT_KEY]: ROUTE_MANIFEST_NOTICE,
      version: 1,
      routes,
    }),
    appRouteOnly,
    navigationOnly,
    unmountedRouteFiles,
  }
}

/**
 * Sort source tags alphabetically for stable manifest output.
 *
 * @param sources - Source tags on a route entry
 * @returns Sorted copy of the source tags
 */
function sortedSources(sources: NormalizedRoute['sources']): NormalizedRoute['sources'] {
  return [...sources].sort((a, b) => a.localeCompare(b))
}

/**
 * Return a route entry with stable field ordering for serialization.
 *
 * @param route - Route entry to normalize
 * @returns Copy with sorted `sources` and consistent key order
 */
function sortRouteFields(route: NormalizedRoute): NormalizedRoute {
  const sorted: NormalizedRoute = {
    template: route.template,
    parameters: [...route.parameters],
    kind: route.kind,
    sources: sortedSources(route.sources),
  }
  if (route.redirectTo !== undefined) {
    sorted.redirectTo = route.redirectTo
  }
  return sorted
}

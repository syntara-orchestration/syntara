import { execFileSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { afterEach, describe, expect, it } from 'vitest'

import { SOURCE_PARITY_EXCEPTIONS, buildRouteManifest } from './build-route-manifest'
import {
  collectAppRoutePaths,
  collectMountedRouterRoutes,
  collectNavigationPathsFromSource,
  parseAppRouteCatalog,
} from './collect-routes'
import { diffRouteManifest } from './diff-route-manifest'
import { getManifestPath, getPackageRoot, readCommittedManifest, writeManifest } from './manifest-io'
import { ROUTE_MANIFEST_COMMENT_KEY, ROUTE_MANIFEST_NOTICE, type RouteManifest } from './route-manifest-schema'
import { checkRouteBaseline, updateRouteBaseline } from './run-route-baseline'

describe('route baseline', () => {
  const pkgRoot = getPackageRoot()
  const { manifest, appRouteOnly, navigationOnly, unmountedRouteFiles } = buildRouteManifest({
    pkgRoot,
  })
  const tempRoots: string[] = []

  afterEach(() => {
    for (const root of tempRoots.splice(0)) {
      rmSync(root, { recursive: true, force: true })
    }
  })

  function makeTempPackageRoot(): string {
    const root = mkdtempSync(join(tmpdir(), 'route-baseline-'))
    tempRoots.push(root)
    return root
  }

  it('matches the committed route-baseline/manifest.gen.json with deep equality', () => {
    const committed = readCommittedManifest(pkgRoot)
    const diff = diffRouteManifest(committed, manifest)

    if (diff.added.length || diff.removed.length || diff.changed.length) {
      const lines = [
        'Route baseline drift detected. If this change is intentional, run:',
        '  npm run route-baseline:update',
        '',
        diff.removed.length ? `Removed:\n  - ${diff.removed.join('\n  - ')}` : '',
        diff.added.length ? `Added:\n  - ${diff.added.join('\n  - ')}` : '',
        diff.changed.length ? `Changed:\n  - ${diff.changed.map((change) => change.template).join('\n  - ')}` : '',
      ].filter(Boolean)
      throw new Error(lines.join('\n'))
    }

    expect(manifest).toStrictEqual(committed)
  })

  it('has no AppRoute templates missing from the manifest (except known exceptions)', () => {
    expect(appRouteOnly).toStrictEqual([])
  })

  it('has no navigation templates missing from the manifest', () => {
    expect(navigationOnly).toStrictEqual([])
  })

  it('has no unmounted route modules with createRoute', () => {
    expect(unmountedRouteFiles).toStrictEqual([])
  })

  it('keeps SOURCE_PARITY_EXCEPTIONS limited to documented non-manifest gaps', () => {
    expect(SOURCE_PARITY_EXCEPTIONS.has('/auth/test-signin-callback')).toBe(false)
    expect(SOURCE_PARITY_EXCEPTIONS.has('/dashboard')).toBe(true)
    for (const template of SOURCE_PARITY_EXCEPTIONS) {
      expect(manifest.routes.some((route) => route.template === template)).toBe(false)
    }
  })

  it('builds a stable sorted manifest from the real package sources', () => {
    expect(manifest[ROUTE_MANIFEST_COMMENT_KEY]).toBe(ROUTE_MANIFEST_NOTICE)
    expect(manifest.version).toBe(1)
    expect(manifest.routes.length).toBeGreaterThanOrEqual(47)

    const templates = manifest.routes.map((route) => route.template)
    expect(templates).toStrictEqual([...templates].sort((a, b) => a.localeCompare(b)))
    expect(new Set(templates).size).toBe(templates.length)

    expect(manifest.routes.some((route) => route.template === '/workflows')).toBe(true)
    expect(manifest.routes.some((route) => route.kind === 'redirect')).toBe(true)
    expect(manifest.routes.some((route) => route.kind === 'fallback')).toBe(true)
    expect(manifest.routes.some((route) => route.kind === 'app')).toBe(true)
  })

  it('records the configuration redirect', () => {
    const route = manifest.routes.find((entry) => entry.template === '/configuration')
    expect(route).toMatchObject({
      parameters: [],
      kind: 'redirect',
      redirectTo: '/configuration/integrations',
    })
    expect(route?.sources).toContain('router')
  })

  it('records the not-found fallback from __root.ts', () => {
    const route = manifest.routes.find((entry) => entry.template === '*')
    expect(route).toStrictEqual({
      template: '*',
      parameters: [],
      kind: 'fallback',
      redirectTo: '/workflows',
      sources: ['router'],
    })
  })

  it('records the App.tsx auth escape hatch from live source', () => {
    const route = manifest.routes.find((entry) => entry.template === '/auth/test-signin-callback')
    expect(route).toMatchObject({
      kind: 'app',
      parameters: [],
    })
    expect(route?.sources).toEqual(expect.arrayContaining(['app', 'appRoute']))
  })

  it('collects only mounted router modules from the live tree', () => {
    const treeSource = readFileSync(join(pkgRoot, 'src/app/tanstackRouteTree.tsx'), 'utf-8')
    const { routes: routerRoutes, unmountedRouteFiles: unmounted } = collectMountedRouterRoutes(
      join(pkgRoot, 'src/app/routes'),
      treeSource
    )
    expect(unmounted).toStrictEqual([])

    const routerTemplates = new Set(routerRoutes.map((route) => route.template))
    expect(routerTemplates.has('/workflows')).toBe(true)
    expect(routerTemplates.has('/configuration')).toBe(true)
    expect(routerRoutes.find((route) => route.template === '/configuration')).toMatchObject({
      kind: 'redirect',
      redirectTo: '/configuration/integrations',
    })

    const appRouteSource = readFileSync(join(pkgRoot, 'src/app/AppRoute.tsx'), 'utf-8')
    const navigationSource = readFileSync(join(pkgRoot, 'src/app/navigationItems.tsx'), 'utf-8')
    const appRouteCatalog = parseAppRouteCatalog(appRouteSource)

    const appRoutePaths = collectAppRoutePaths(appRouteSource)
    expect(appRoutePaths).toContain('/workflows')
    expect(appRoutePaths).toContain('/system-administration/access-management/users/$userId')

    const navigationPaths = collectNavigationPathsFromSource(navigationSource, appRouteCatalog)
    expect(navigationPaths).toContain('/workflows')
    expect(navigationPaths).toContain('/approvals')
  })

  it('round-trips a generated manifest through writeManifest and readCommittedManifest', () => {
    const tempRoot = makeTempPackageRoot()
    mkdirSync(join(tempRoot, 'route-baseline'), { recursive: true })

    const writtenPath = writeManifest(manifest, tempRoot)

    expect(writtenPath).toBe(getManifestPath(tempRoot))
    expect(readCommittedManifest(tempRoot)).toStrictEqual(manifest)

    const raw = readFileSync(writtenPath, 'utf-8')
    expect(raw.endsWith('\n')).toBe(true)
    expect(JSON.parse(raw)).toStrictEqual(manifest)
  })

  it('checkRouteBaseline passes against the committed package baseline', () => {
    const result = checkRouteBaseline(pkgRoot)

    expect(result.ok).toBe(true)
    expect(result.messages).toStrictEqual([])
    expect(result.diff).toStrictEqual({ added: [], removed: [], changed: [] })
    expect(result.unmountedRouteFiles).toStrictEqual([])
    expect(result.manifest).toStrictEqual(readCommittedManifest(pkgRoot))
  })

  it('checkRouteBaseline fails when the committed manifest is stale', () => {
    const tempRoot = makeTempPackageRoot()
    copyRouteSources(pkgRoot, tempRoot)

    const built = buildRouteManifest({ pkgRoot: tempRoot })
    const stale: RouteManifest = {
      [ROUTE_MANIFEST_COMMENT_KEY]: ROUTE_MANIFEST_NOTICE,
      version: 1,
      routes: built.manifest.routes.filter((route) => route.template !== '/workflows'),
    }
    writeManifest(stale, tempRoot)

    const result = checkRouteBaseline(tempRoot)
    expect(result.ok).toBe(false)
    expect(result.diff.added).toContain('/workflows')
    expect(result.messages.some((line) => line.includes('Added routes:'))).toBe(true)
  })

  it('checkRouteBaseline fails when App.tsx escape hatch path changes', () => {
    const tempRoot = makeTempPackageRoot()
    copyRouteSources(pkgRoot, tempRoot)
    updateRouteBaseline(tempRoot)

    const appPath = join(tempRoot, 'src/app/App.tsx')
    const appSource = readFileSync(appPath, 'utf-8').replace(
      'AppRoute.Auth.TestSignInCallback',
      "'/auth/moved-callback'"
    )
    writeFileSync(appPath, appSource)

    const result = checkRouteBaseline(tempRoot)
    expect(result.ok).toBe(false)
    expect(result.diff.added).toContain('/auth/moved-callback')
    expect(result.diff.removed).toContain('/auth/test-signin-callback')
  })

  it('checkRouteBaseline fails when __root not-found target changes', () => {
    const tempRoot = makeTempPackageRoot()
    copyRouteSources(pkgRoot, tempRoot)
    updateRouteBaseline(tempRoot)

    const rootPath = join(tempRoot, 'src/app/routes/__root.ts')
    writeFileSync(rootPath, readFileSync(rootPath, 'utf-8').replace("to: '/workflows'", "to: '/approvals'"))

    const result = checkRouteBaseline(tempRoot)
    expect(result.ok).toBe(false)
    expect(result.diff.changed.some((change) => change.template === '*')).toBe(true)
  })

  it('checkRouteBaseline fails for unmounted createRoute modules', () => {
    const tempRoot = makeTempPackageRoot()
    copyRouteSources(pkgRoot, tempRoot)
    updateRouteBaseline(tempRoot)

    writeFileSync(
      join(tempRoot, 'src/app/routes/orphan.tsx'),
      `import { createRoute } from '@tanstack/react-router'
import { rootRoute } from './__root'
export const orphanRoutes = [
  createRoute({ getParentRoute: () => rootRoute, path: '/orphan-page' }),
]
`
    )

    const result = checkRouteBaseline(tempRoot)
    expect(result.ok).toBe(false)
    expect(result.unmountedRouteFiles).toContain('orphan.tsx')
    expect(result.messages.some((line) => line.includes('Unmounted route modules'))).toBe(true)
  })

  it('updateRouteBaseline refuses to write when parity gaps remain', () => {
    const tempRoot = makeTempPackageRoot()
    copyRouteSources(pkgRoot, tempRoot)

    const appRoutePath = join(tempRoot, 'src/app/AppRoute.tsx')
    writeFileSync(
      appRoutePath,
      `${readFileSync(appRoutePath, 'utf-8')}\nexport const ExtraOnlyInAppRoute = '/parity-gap-only'\n`
    )

    // Rebuild AppRoute import won't pick up the string unless it's a path literal
    // inside the file — collectAppRoutePaths scrapes all '/...' literals.
    expect(() => updateRouteBaseline(tempRoot)).toThrow(/Refusing to update route baseline/)
  })

  it('updateRouteBaseline writes a manifest that checkRouteBaseline accepts', () => {
    const tempRoot = makeTempPackageRoot()
    copyRouteSources(pkgRoot, tempRoot)

    const update = updateRouteBaseline(tempRoot)
    expect(update.routeCount).toBeGreaterThanOrEqual(47)
    expect(readFileSync(update.path, 'utf-8').length).toBeGreaterThan(0)

    const check = checkRouteBaseline(tempRoot)
    expect(check.ok).toBe(true)
    expect(check.manifest.routes).toHaveLength(update.routeCount)
  })

  it('updateRouteBaseline formats the manifest with Prettier', () => {
    const tempRoot = makeTempPackageRoot()
    copyRouteSources(pkgRoot, tempRoot)

    // Point Prettier at the real frontend config by nesting under a fake packages/ path.
    const nestedRoot = join(tempRoot, 'packages', 'syntara-ui')
    copyRouteSources(pkgRoot, nestedRoot)
    writeFileSync(join(tempRoot, 'package.json'), '{ "name": "frontend-fixture" }\n')

    const update = updateRouteBaseline(nestedRoot)
    expect(() =>
      execFileSync('npx', ['prettier', '--check', update.path], {
        cwd: tempRoot,
        stdio: 'pipe',
      })
    ).not.toThrow()
  })
})

/**
 * Copy only the source files the baseline builder reads into a temp package root.
 */
function copyRouteSources(fromPkgRoot: string, toPkgRoot: string) {
  const relativeFiles = [
    'src/app/App.tsx',
    'src/app/AppRoute.tsx',
    'src/app/navigationItems.tsx',
    'src/app/tanstackRouteTree.tsx',
    'src/app/routes/__root.ts',
    ...listRouteModules(fromPkgRoot),
  ]

  for (const relative of relativeFiles) {
    const from = join(fromPkgRoot, relative)
    const to = join(toPkgRoot, relative)
    mkdirSync(join(to, '..'), { recursive: true })
    writeFileSync(to, readFileSync(from))
  }
}

/**
 * List relative paths of router module files under `src/app/routes`.
 */
function listRouteModules(pkgRoot: string): string[] {
  const routesDir = join(pkgRoot, 'src/app/routes')
  return readdirSync(routesDir)
    .filter((name) => (name.endsWith('.tsx') || name.endsWith('.ts')) && !name.includes('.test.'))
    .map((name) => `src/app/routes/${name}`)
}

import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { afterEach, describe, expect, it } from 'vitest'

import { SOURCE_PARITY_EXCEPTIONS, buildRouteManifest } from './build-route-manifest'
import { collectAppRoutePaths } from './collect-routes'
import { getManifestPath, readCommittedManifest, writeManifest } from './manifest-io'
import { ROUTE_MANIFEST_COMMENT_KEY, ROUTE_MANIFEST_NOTICE, type RouteManifest } from './route-manifest-schema'
import { checkRouteBaseline, updateRouteBaseline } from './run-route-baseline'

describe('route baseline tooling', () => {
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

  function makeFixturePackageRoot(): string {
    const toPkgRoot = makeTempPackageRoot()
    for (const [relative, source] of Object.entries(FIXTURE_ROUTE_SOURCES)) {
      const to = join(toPkgRoot, relative)
      mkdirSync(join(to, '..'), { recursive: true })
      writeFileSync(to, source)
    }
    return toPkgRoot
  }

  it('keeps SOURCE_PARITY_EXCEPTIONS limited to documented non-manifest gaps', () => {
    const pkgRoot = makeFixturePackageRoot()
    const { manifest } = buildRouteManifest({ pkgRoot })

    expect(SOURCE_PARITY_EXCEPTIONS.has('/auth/test-signin-callback')).toBe(false)
    expect(SOURCE_PARITY_EXCEPTIONS.has('/dashboard')).toBe(true)
    for (const template of SOURCE_PARITY_EXCEPTIONS) {
      expect(manifest.routes.some((route) => route.template === template)).toBe(false)
    }
  })

  it('round-trips a generated manifest through writeManifest and readCommittedManifest', () => {
    const pkgRoot = makeFixturePackageRoot()
    const { manifest } = buildRouteManifest({ pkgRoot })
    const tempRoot = makeTempPackageRoot()
    mkdirSync(join(tempRoot, 'scripts/route-baseline'), { recursive: true })

    const writtenPath = writeManifest(manifest, tempRoot)

    expect(writtenPath).toBe(getManifestPath(tempRoot))
    expect(readCommittedManifest(tempRoot)).toStrictEqual(manifest)

    const raw = readFileSync(writtenPath, 'utf-8')
    expect(raw.endsWith('\n')).toBe(true)
    expect(JSON.parse(raw)).toStrictEqual(manifest)
  })

  it('checkRouteBaseline fails when the committed manifest is stale', () => {
    const tempRoot = makeFixturePackageRoot()

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
    expect(result.messages.some((line) => line.includes('Next steps:'))).toBe(true)
  })

  it('checkRouteBaseline fails when App.tsx escape hatch path changes', () => {
    const tempRoot = makeFixturePackageRoot()
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
    const tempRoot = makeFixturePackageRoot()
    updateRouteBaseline(tempRoot)

    const rootPath = join(tempRoot, 'src/app/routes/__root.ts')
    writeFileSync(rootPath, readFileSync(rootPath, 'utf-8').replace("to: '/workflows'", "to: '/approvals'"))

    const result = checkRouteBaseline(tempRoot)
    expect(result.ok).toBe(false)
    expect(result.diff.changed.some((change) => change.template === '*')).toBe(true)
  })

  it('checkRouteBaseline fails for unmounted createRoute modules', () => {
    const tempRoot = makeFixturePackageRoot()
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
    const tempRoot = makeFixturePackageRoot()

    const appRoutePath = join(tempRoot, 'src/app/AppRoute.tsx')
    writeFileSync(
      appRoutePath,
      `${readFileSync(appRoutePath, 'utf-8')}\nexport const ExtraOnlyInAppRoute = '/parity-gap-only'\n`
    )

    // collectAppRoutePaths scrapes all '/...' literals in AppRoute source.
    expect(() => updateRouteBaseline(tempRoot)).toThrow(/Refusing to update route baseline/)
  })

  it('updateRouteBaseline writes a manifest that checkRouteBaseline accepts', () => {
    const tempRoot = makeFixturePackageRoot()

    const update = updateRouteBaseline(tempRoot)
    expect(update.routeCount).toBe(3)
    expect(readFileSync(update.path, 'utf-8').length).toBeGreaterThan(0)

    const check = checkRouteBaseline(tempRoot)
    expect(check.ok).toBe(true)
    expect(check.manifest.routes).toHaveLength(update.routeCount)
  })

  it('buildRouteManifest output is sorted, unique, and versioned', () => {
    const tempRoot = makeFixturePackageRoot()
    const { manifest } = buildRouteManifest({ pkgRoot: tempRoot })

    expect(manifest[ROUTE_MANIFEST_COMMENT_KEY]).toBe(ROUTE_MANIFEST_NOTICE)
    expect(manifest.version).toBe(1)
    expect(manifest.routes).toHaveLength(3)

    const templates = manifest.routes.map((route) => route.template)
    expect(templates).toStrictEqual([...templates].sort((a, b) => a.localeCompare(b)))
    expect(new Set(templates).size).toBe(templates.length)
  })

  it('collectAppRoutePaths scrapes absolute path literals from AppRoute source', () => {
    const appRouteSource = FIXTURE_ROUTE_SOURCES['src/app/AppRoute.tsx']
    expect(appRouteSource).toBeDefined()
    const paths = collectAppRoutePaths(appRouteSource)
    expect(paths).toStrictEqual(['/auth/test-signin-callback', '/workflows'])
  })
})

/**
 * Static route package fixture consumed by the baseline builder tests.
 *
 * Keep this independent of the live application route topology: the contract
 * CLI, rather than Vitest, verifies the committed manifest against live sources.
 */
const FIXTURE_ROUTE_SOURCES = {
  'src/app/App.tsx': `if (globalThis.location.pathname === AppRoute.Auth.TestSignInCallback) return null\n`,
  'src/app/AppRoute.tsx': `export const AppRoute = {\n  Workflows: { Root: '/workflows' },\n  Auth: { TestSignInCallback: '/auth/test-signin-callback' },\n}\n`,
  'src/app/navigationItems.tsx': `const items = [{ path: AppRoute.Workflows.Root }]\n`,
  'src/app/tanstackRouteTree.tsx': `import { workflowsRoutes } from './routes/workflows'\nexport const tree = rootRoute.addChildren([...workflowsRoutes])\n`,
  'src/app/routes/__root.ts': `navigate({ to: '/workflows', replace: true })\n`,
  'src/app/routes/workflows.tsx': `export const workflowsRoutes = [\n  createRoute({ getParentRoute: () => rootRoute, path: '/workflows' }),\n]\n`,
} as const

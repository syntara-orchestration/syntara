import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { afterEach, describe, expect, it } from 'vitest'

import { SOURCE_PARITY_EXCEPTIONS, buildRouteManifest } from './build-route-manifest'
import { collectAppRoutePaths } from './collect-routes'
import { getManifestPath, getPackageRoot, readCommittedManifest, writeManifest } from './manifest-io'
import { ROUTE_MANIFEST_COMMENT_KEY, ROUTE_MANIFEST_NOTICE, type RouteManifest } from './route-manifest-schema'
import { checkRouteBaseline, updateRouteBaseline } from './run-route-baseline'

describe('route baseline tooling', () => {
  const pkgRoot = getPackageRoot()
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

  it('keeps SOURCE_PARITY_EXCEPTIONS limited to documented non-manifest gaps', () => {
    const { manifest } = buildRouteManifest({ pkgRoot })

    expect(SOURCE_PARITY_EXCEPTIONS.has('/auth/test-signin-callback')).toBe(false)
    expect(SOURCE_PARITY_EXCEPTIONS.has('/dashboard')).toBe(true)
    for (const template of SOURCE_PARITY_EXCEPTIONS) {
      expect(manifest.routes.some((route) => route.template === template)).toBe(false)
    }
  })

  it('round-trips a generated manifest through writeManifest and readCommittedManifest', () => {
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
    expect(result.messages.some((line) => line.includes('Next steps:'))).toBe(true)
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

    // collectAppRoutePaths scrapes all '/...' literals in AppRoute source.
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

  it('buildRouteManifest output is sorted, unique, and versioned', () => {
    const tempRoot = makeTempPackageRoot()
    copyRouteSources(pkgRoot, tempRoot)
    const { manifest } = buildRouteManifest({ pkgRoot: tempRoot })

    expect(manifest[ROUTE_MANIFEST_COMMENT_KEY]).toBe(ROUTE_MANIFEST_NOTICE)
    expect(manifest.version).toBe(1)
    expect(manifest.routes.length).toBeGreaterThanOrEqual(47)

    const templates = manifest.routes.map((route) => route.template)
    expect(templates).toStrictEqual([...templates].sort((a, b) => a.localeCompare(b)))
    expect(new Set(templates).size).toBe(templates.length)
  })

  it('collectAppRoutePaths scrapes absolute path literals from AppRoute source', () => {
    const appRouteSource = readFileSync(join(pkgRoot, 'src/app/AppRoute.tsx'), 'utf-8')
    const paths = collectAppRoutePaths(appRouteSource)
    expect(paths.length).toBeGreaterThan(0)
    expect(paths.every((path) => path.startsWith('/'))).toBe(true)
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

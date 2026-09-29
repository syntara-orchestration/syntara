/**
 * Baseline enforcement script for visual regression testing.
 *
 * Catches four failure modes:
 *   1. A new route was added to AppRoute.tsx but not to the page registry
 *   2. A registry path doesn't match any route in AppRoute.tsx (stale/moved route)
 *   3. A route is in the page registry but has no committed baseline screenshot
 *   4. A baseline PNG exists but has no matching entry in the page registry (orphan)
 *
 * Usage:
 *   npm exec tsx -- scripts/visual-regression/check-visual-baselines.ts
 *
 * Exit codes:
 *   0 — all routes covered, all baselines present
 *   1 — missing coverage or missing baselines
 */

import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs'
import { resolve, dirname, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const pkgRoot = resolve(__dirname, '../..')

// ---------------------------------------------------------------------------
// 1. Extract all route paths from AppRoute.tsx
// ---------------------------------------------------------------------------
const appRoutePath = resolve(pkgRoot, 'src/app/AppRoute.tsx')
const appRouteSource = readFileSync(appRoutePath, 'utf-8')

// Match all string literals that look like route paths: '/some/path'
const routePathRegex = /['"](\/.+?)['"]/g
const allAppRoutes = new Set<string>()

for (const match of appRouteSource.matchAll(routePathRegex)) {
  allAppRoutes.add(match[1])
}

// ---------------------------------------------------------------------------
// 2. Import the page registry to get resolved paths (handles AppRoute imports)
// ---------------------------------------------------------------------------
const { pages, loginPages, allExcludedRoutes } = await import(
  resolve(pkgRoot, 'e2e/visual-regression/page-registry.ts')
)

const coveredConcretePaths = new Set<string>(pages.map((p: { path: string }) => p.path))
const excludedRoutes = new Set<string>(allExcludedRoutes as string[])

// ---------------------------------------------------------------------------
// 3. Normalize parameterized routes for comparison
//    AppRoute.tsx has :param placeholders; the registry uses concrete mock IDs
// ---------------------------------------------------------------------------

function matchesTemplate(template: string, concretePath: string): boolean {
  const tParts = template.split('/')
  const cParts = concretePath.split('/')

  if (tParts.length !== cParts.length) {
    const tail = tParts[tParts.length - 1]
    const isOptionalTail = tail?.startsWith(':') && tail.endsWith('?') && tParts.length === cParts.length + 1
    if (!isOptionalTail) return false
  }

  return tParts.every((tSeg, i) => {
    if (i >= cParts.length) return tSeg.startsWith(':') && tSeg.endsWith('?')
    if (tSeg.startsWith(':')) return true
    return tSeg === cParts[i]
  })
}

// Build set of AppRoute templates that are covered (by concrete paths or exclusions)
const uncoveredRoutes: string[] = []

for (const route of allAppRoutes) {
  // Check if explicitly excluded
  if (excludedRoutes.has(route)) continue

  // Check if covered by a concrete path in the registry
  const isCovered = [...coveredConcretePaths].some((cp) => matchesTemplate(route, cp))
  // Check for exact match (non-parameterized routes)
  const isExact = coveredConcretePaths.has(route)

  if (!isCovered && !isExact) {
    uncoveredRoutes.push(route)
  }
}

// ---------------------------------------------------------------------------
// 3b. Detect stale registry paths (registry → AppRoute reverse check)
// ---------------------------------------------------------------------------
const staleRegistryPaths: string[] = []

for (const concretePath of coveredConcretePaths) {
  const matchesAny = [...allAppRoutes].some((template) => matchesTemplate(template, concretePath))
  if (!matchesAny) {
    staleRegistryPaths.push(concretePath)
  }
}

// ---------------------------------------------------------------------------
// 4. Check that baseline screenshots exist for every registry entry
// ---------------------------------------------------------------------------
const snapshotDir = resolve(pkgRoot, 'e2e/visual-regression/page-screenshots.spec.ts-snapshots')

const loginPageEntries: Array<{ section: string; name: string }> = (
  loginPages as Array<{ section: string; name: string }>
).map((p) => ({
  section: p.section,
  name: p.name,
}))

const registryEntries: Array<{ section: string; name: string }> = [
  ...pages.map((p: { section: string; name: string }) => ({
    section: p.section,
    name: p.name,
  })),
  ...loginPageEntries,
]

const missingBaselines: { entry: string; expectedPath: string }[] = []

for (const entry of registryEntries) {
  const baselinePath = resolve(snapshotDir, entry.section, `${entry.name}-linux.png`)
  if (!existsSync(baselinePath)) {
    missingBaselines.push({
      entry: `${entry.section}/${entry.name}`,
      expectedPath: baselinePath.replace(pkgRoot + '/', ''),
    })
  }
}

// ---------------------------------------------------------------------------
// 5. Detect orphan baselines (PNGs with no matching registry entry)
// ---------------------------------------------------------------------------

/** Recursively collect all `-linux.png` files under a directory. */
function collectLinuxPngs(dir: string): string[] {
  const results: string[] = []
  if (!existsSync(dir)) return results
  for (const entry of readdirSync(dir)) {
    const full = resolve(dir, entry)
    if (statSync(full).isDirectory()) {
      results.push(...collectLinuxPngs(full))
    } else if (entry.endsWith('-linux.png')) {
      results.push(full)
    }
  }
  return results
}

const allBaselinePngs = collectLinuxPngs(snapshotDir)

// Build a set of expected baseline paths from registry entries
const expectedBaselinePaths = new Set(
  registryEntries.map((e) => resolve(snapshotDir, e.section, `${e.name}-linux.png`))
)

const orphanBaselines = allBaselinePngs.filter((p) => !expectedBaselinePaths.has(p))

// ---------------------------------------------------------------------------
// 6. Report results
// ---------------------------------------------------------------------------
let hasErrors = false

if (uncoveredRoutes.length > 0) {
  hasErrors = true
  console.error('\n--- Routes missing from page registry ---')
  console.error('These routes exist in AppRoute.tsx but have no entry in page-registry.ts:')
  for (const route of uncoveredRoutes.sort()) {
    console.error(`  - ${route}`)
  }
  console.error('\nTo fix: add an entry to e2e/visual-regression/page-registry.ts')
  console.error('        or add to excludedUnimplemented/excludedDynamic if intentionally skipped.\n')
}

if (missingBaselines.length > 0) {
  hasErrors = true
  console.error('\n--- Missing baseline screenshots ---')
  console.error('These pages are registered but have no committed Linux baseline:')
  for (const { entry, expectedPath } of missingBaselines) {
    console.error(`  - ${entry}`)
    console.error(`    Expected: ${expectedPath}`)
  }
  console.error('\nTo fix: run `npx playwright test page-screenshots --update-snapshots` on Linux')
  console.error(
    '        or use Docker: docker run --rm -v $(pwd):/work -w /work/packages/syntara-ui \\\n' +
      '          mcr.microsoft.com/playwright:v1.59.0-noble \\\n' +
      '          npx playwright test e2e/visual-regression/page-screenshots --update-snapshots\n'
  )
}

if (staleRegistryPaths.length > 0) {
  hasErrors = true
  console.error('\n--- Stale registry paths ---')
  console.error("These paths are in page-registry.ts but don't match any route in AppRoute.tsx:")
  for (const p of staleRegistryPaths.sort()) {
    console.error(`  - ${p}`)
  }
  console.error('\nTo fix: update the path in page-registry.ts to match the current route in AppRoute.tsx.')
  console.error('        This usually means a route was moved but the registry was not updated.\n')
}

if (orphanBaselines.length > 0) {
  hasErrors = true
  console.error('\n--- Orphan baseline screenshots ---')
  console.error('These baseline PNGs have no matching entry in page-registry.ts:')
  for (const p of orphanBaselines) {
    console.error(`  - ${relative(pkgRoot, p)}`)
  }
  console.error('\nTo fix: delete the orphan PNGs, or re-add the registry entry if the page still exists.\n')
}

if (hasErrors) {
  process.exit(1)
} else {
  console.log('All routes covered, all baselines present, no orphans, no stale paths.')
  console.log(`  Routes in AppRoute.tsx: ${allAppRoutes.size} (${excludedRoutes.size} excluded)`)
  console.log(
    `  Pages in registry: ${registryEntries.length} (${loginPageEntries.length} login + ${registryEntries.length - loginPageEntries.length} routes)`
  )
  console.log(`  Baseline PNGs: ${allBaselinePngs.length}`)
  process.exit(0)
}

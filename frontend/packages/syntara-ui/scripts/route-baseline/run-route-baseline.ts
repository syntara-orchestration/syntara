import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync } from 'node:fs'
import { join, relative } from 'node:path'

import { buildRouteManifest } from './build-route-manifest'
import { diffRouteManifest, type RouteManifestDiff } from './diff-route-manifest'
import { getPackageRoot, getRouteBaselineDir, readCommittedManifest, writeManifest } from './manifest-io'
import type { RouteManifest } from './route-manifest-schema'

/**
 * Result of comparing the committed baseline to a fresh generate.
 */
export type CheckRouteBaselineResult = {
  /** `true` when the committed manifest matches and source parity is clean. */
  ok: boolean
  /** Freshly generated manifest. */
  manifest: RouteManifest
  /** Diff between committed and generated manifests. */
  diff: RouteManifestDiff
  /** AppRoute templates missing from the generated manifest. */
  appRouteOnly: string[]
  /** Navigation templates missing from the generated manifest. */
  navigationOnly: string[]
  /** Route modules with `createRoute` that are not mounted in the tree. */
  unmountedRouteFiles: string[]
  /** Human-readable lines describing failures (empty when `ok`). */
  messages: string[]
}

/**
 * Result of regenerating and writing the committed baseline.
 */
export type UpdateRouteBaselineResult = {
  /** Absolute path written. */
  path: string
  /** Number of routes in the written manifest. */
  routeCount: number
}

/**
 * Compare the committed manifest to a fresh build without exiting the process.
 *
 * Used by `npm run route-baseline:check` and by fixture-based Vitest cases.
 *
 * @param pkgRoot - Package root containing sources and `scripts/route-baseline/`
 * @returns Check result with diff and message lines
 */
export function checkRouteBaseline(pkgRoot = getPackageRoot()): CheckRouteBaselineResult {
  const committed = readCommittedManifest(pkgRoot)
  const { manifest, appRouteOnly, navigationOnly, unmountedRouteFiles } = buildRouteManifest({
    pkgRoot,
  })
  const diff = diffRouteManifest(committed, manifest)
  const ok =
    diff.added.length === 0 &&
    diff.removed.length === 0 &&
    diff.changed.length === 0 &&
    appRouteOnly.length === 0 &&
    navigationOnly.length === 0 &&
    unmountedRouteFiles.length === 0

  return {
    ok,
    manifest,
    diff,
    appRouteOnly,
    navigationOnly,
    unmountedRouteFiles,
    messages: formatCheckMessages({
      ok,
      diff,
      appRouteOnly,
      navigationOnly,
      unmountedRouteFiles,
    }),
  }
}

/**
 * Build human-readable failure lines for a baseline check.
 *
 * @param input - Diff and parity gaps from {@link checkRouteBaseline}
 * @returns Message lines (empty when the check passed)
 */
function formatCheckMessages(input: {
  ok: boolean
  diff: RouteManifestDiff
  appRouteOnly: string[]
  navigationOnly: string[]
  unmountedRouteFiles: string[]
}): string[] {
  if (input.ok) return []

  const messages: string[] = []
  appendTemplateList(messages, 'Removed routes:', input.diff.removed)
  appendTemplateList(messages, 'Added routes:', input.diff.added)

  if (input.diff.changed.length > 0) {
    messages.push('Changed routes:')
    for (const change of input.diff.changed) {
      messages.push(`  - ${change.template}`)
      messages.push(`      before: ${JSON.stringify(change.before)}`)
      messages.push(`      after:  ${JSON.stringify(change.after)}`)
    }
  }

  appendTemplateList(messages, 'AppRoute templates missing from manifest:', input.appRouteOnly)
  appendTemplateList(messages, 'Navigation templates missing from manifest:', input.navigationOnly)
  appendTemplateList(messages, 'Unmounted route modules with createRoute:', input.unmountedRouteFiles)

  messages.push('')
  messages.push('Next steps:')
  messages.push('')
  messages.push('If this change is intentional:')
  messages.push('  1. From the frontend workspace (or @syntara/ui package):')
  messages.push('       npm run route-baseline:update')
  messages.push('  2. Review scripts/route-baseline/manifest.gen.json')
  messages.push('  3. Commit the updated manifest in the same PR')
  messages.push('')
  messages.push('If this change is unintentional:')
  messages.push('  Fix the route sources (src/app/routes/*, AppRoute.tsx,')
  messages.push('  navigationItems.tsx, tanstackRouteTree.tsx, App.tsx, or routes/__root.ts),')
  messages.push('  then re-run: npm run route-baseline:check')
  messages.push('')
  messages.push(`Docs: ${routeBaselineReadmeHint()}`)
  return messages
}

/**
 * Point at the route-baseline README without hard-coding a monorepo path.
 *
 * Prefers a path relative to the current working directory when possible.
 *
 * @returns Human-readable docs location
 */
function routeBaselineReadmeHint(): string {
  const readmePath = join(getRouteBaselineDir(), 'README.md')
  const fromCwd = relative(process.cwd(), readmePath)
  if (fromCwd && !fromCwd.startsWith('..')) {
    return fromCwd
  }
  return 'scripts/route-baseline/README.md (in the @syntara/ui package)'
}

/**
 * Append a titled bullet list when the template list is non-empty.
 *
 * @param messages - Mutable message buffer
 * @param title - Section heading
 * @param templates - Path templates to list
 */
function appendTemplateList(messages: string[], title: string, templates: string[]): void {
  if (templates.length === 0) return
  messages.push(title)
  for (const template of templates) messages.push(`  - ${template}`)
}

/**
 * Regenerate the route baseline and write `scripts/route-baseline/manifest.gen.json`.
 *
 * Refuses to write when AppRoute/navigation parity gaps or unmounted route
 * modules are present — fix those first or extend `SOURCE_PARITY_EXCEPTIONS`
 * with a documented reason.
 *
 * @param pkgRoot - Package root to read sources from and write the manifest into
 * @returns Write result including path and route count
 * @throws When parity gaps or unmounted route modules would be committed
 */
export function updateRouteBaseline(pkgRoot = getPackageRoot()): UpdateRouteBaselineResult {
  const { manifest, appRouteOnly, navigationOnly, unmountedRouteFiles } = buildRouteManifest({
    pkgRoot,
  })

  if (appRouteOnly.length > 0 || navigationOnly.length > 0 || unmountedRouteFiles.length > 0) {
    const parityLines = formatCheckMessages({
      ok: false,
      diff: { added: [], removed: [], changed: [] },
      appRouteOnly,
      navigationOnly,
      unmountedRouteFiles,
    })
    // Drop the shared "Next steps" remediation — update has its own guidance.
    const nextStepsIndex = parityLines.indexOf('Next steps:')
    const gapLines = (nextStepsIndex === -1 ? parityLines : parityLines.slice(0, nextStepsIndex)).filter(
      (line) => line !== ''
    )

    const lines = [
      'Refusing to update route baseline while source parity gaps remain:',
      ...gapLines,
      '',
      'Add a documented SOURCE_PARITY_EXCEPTIONS entry only for intentional gaps,',
      'or mount/remove the orphan route modules, then retry.',
    ]
    throw new Error(lines.join('\n'))
  }

  mkdirSync(getRouteBaselineDir(pkgRoot), { recursive: true })
  const path = writeManifest(manifest, pkgRoot)
  formatGeneratedManifest(path, pkgRoot)
  return {
    path,
    routeCount: manifest.routes.length,
  }
}

/**
 * Run Prettier on the generated manifest so update output matches `format:check`.
 *
 * @param manifestPath - Absolute path to `manifest.gen.json`
 * @param pkgRoot - UI package root (used to locate the frontend Prettier cwd)
 */
function formatGeneratedManifest(manifestPath: string, pkgRoot: string): void {
  const frontendRoot = join(pkgRoot, '..')
  const cwd = existsSync(join(frontendRoot, 'package.json')) ? frontendRoot : pkgRoot

  try {
    execFileSync('npx', ['prettier', '--write', manifestPath], {
      cwd,
      stdio: 'pipe',
    })
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    throw new Error(`Failed to format ${manifestPath} with Prettier: ${detail}`)
  }
}

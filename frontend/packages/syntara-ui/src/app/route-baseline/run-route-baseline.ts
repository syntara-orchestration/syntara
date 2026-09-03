import { mkdirSync } from 'node:fs'

import { buildRouteManifest } from './build-route-manifest'
import { diffRouteManifest, type RouteManifestDiff } from './diff-route-manifest'
import {
  getPackageRoot,
  getRouteBaselineDir,
  readCommittedManifest,
  writeManifest,
} from './manifest-io'
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
  /** AppRoute parity gaps (warnings; update still writes). */
  appRouteOnly: string[]
  /** Navigation parity gaps (warnings; update still writes). */
  navigationOnly: string[]
}

/**
 * Compare the committed manifest to a fresh build without exiting the process.
 *
 * Used by the CLI script and by Vitest.
 *
 * @param pkgRoot - Package root containing sources and `route-baseline/`
 * @returns Check result with diff and message lines
 */
export function checkRouteBaseline(pkgRoot = getPackageRoot()): CheckRouteBaselineResult {
  const committed = readCommittedManifest(pkgRoot)
  const { manifest, appRouteOnly, navigationOnly } = buildRouteManifest({ pkgRoot })
  const diff = diffRouteManifest(committed, manifest)
  const ok =
    diff.added.length === 0 &&
    diff.removed.length === 0 &&
    diff.changed.length === 0 &&
    appRouteOnly.length === 0 &&
    navigationOnly.length === 0

  return {
    ok,
    manifest,
    diff,
    appRouteOnly,
    navigationOnly,
    messages: formatCheckMessages({ ok, diff, appRouteOnly, navigationOnly }),
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

  messages.push('')
  messages.push('If this change is intentional, run:')
  messages.push('  npm run route-baseline:update --prefix packages/syntara-ui')
  messages.push('and commit route-baseline/manifest.json')
  return messages
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
 * Regenerate the route baseline and write `route-baseline/manifest.json`.
 *
 * @param pkgRoot - Package root to read sources from and write the manifest into
 * @returns Write result including path and route count
 */
export function updateRouteBaseline(pkgRoot = getPackageRoot()): UpdateRouteBaselineResult {
  const { manifest, appRouteOnly, navigationOnly } = buildRouteManifest({ pkgRoot })
  mkdirSync(getRouteBaselineDir(pkgRoot), { recursive: true })
  const path = writeManifest(manifest, pkgRoot)
  return {
    path,
    routeCount: manifest.routes.length,
    appRouteOnly,
    navigationOnly,
  }
}

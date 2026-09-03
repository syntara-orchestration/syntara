import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { stableStringify } from './normalize-route'
import type { RouteManifest } from './types'

const thisDir = dirname(fileURLToPath(import.meta.url))

/**
 * Resolve the `packages/syntara-ui` package root from this module's location.
 *
 * @returns Absolute path to the UI package root
 */
export function getPackageRoot(): string {
  return join(thisDir, '../../..')
}

/**
 * Resolve the committed baseline directory under a package root.
 *
 * @param pkgRoot - UI package root (defaults to this package)
 * @returns Absolute path to `route-baseline/`
 */
export function getRouteBaselineDir(pkgRoot = getPackageRoot()): string {
  return join(pkgRoot, 'route-baseline')
}

/**
 * Resolve the committed manifest file path.
 *
 * @param pkgRoot - UI package root (defaults to this package)
 * @returns Absolute path to `route-baseline/manifest.json`
 */
export function getManifestPath(pkgRoot = getPackageRoot()): string {
  return join(getRouteBaselineDir(pkgRoot), 'manifest.json')
}

/**
 * Read and parse the committed route baseline manifest.
 *
 * @param pkgRoot - UI package root that contains `route-baseline/manifest.json`
 * @returns Parsed manifest object
 */
export function readCommittedManifest(pkgRoot = getPackageRoot()): RouteManifest {
  const raw = readFileSync(getManifestPath(pkgRoot), 'utf-8')
  return JSON.parse(raw) as RouteManifest
}

/**
 * Write a route manifest to `route-baseline/manifest.json` under `pkgRoot`.
 *
 * @param manifest - Manifest to serialize
 * @param pkgRoot - UI package root (or a temp directory in tests)
 * @returns Absolute path written
 */
export function writeManifest(manifest: RouteManifest, pkgRoot = getPackageRoot()): string {
  const path = getManifestPath(pkgRoot)
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, stableStringify(manifest), 'utf-8')
  return path
}

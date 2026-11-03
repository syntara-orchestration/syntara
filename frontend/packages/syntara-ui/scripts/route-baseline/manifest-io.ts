import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { stableStringify } from './normalize-route'
import { routeManifestJsonSchema, routeManifestSchema, type RouteManifest } from './route-manifest-schema'

const thisDir = dirname(fileURLToPath(import.meta.url))

/**
 * Resolve the `packages/syntara-ui` package root from this module's location.
 *
 * @returns Absolute path to the UI package root
 */
export function getPackageRoot(): string {
  return join(thisDir, '../..')
}

/**
 * Resolve the committed baseline directory under a package root.
 *
 * Tooling and the generated artifact both live under `scripts/route-baseline/`.
 *
 * @param pkgRoot - UI package root (defaults to this package)
 * @returns Absolute path to `scripts/route-baseline/`
 */
export function getRouteBaselineDir(pkgRoot = getPackageRoot()): string {
  return join(pkgRoot, 'scripts/route-baseline')
}

/**
 * Resolve the committed manifest file path.
 *
 * @param pkgRoot - UI package root (defaults to this package)
 * @returns Absolute path to `scripts/route-baseline/manifest.gen.json`
 */
export function getManifestPath(pkgRoot = getPackageRoot()): string {
  return join(getRouteBaselineDir(pkgRoot), 'manifest.gen.json')
}

/**
 * Read and parse the committed route baseline manifest.
 *
 * @param pkgRoot - UI package root that contains `scripts/route-baseline/manifest.gen.json`
 * @returns Parsed manifest object
 */
export function readCommittedManifest(pkgRoot = getPackageRoot()): RouteManifest {
  return routeManifestJsonSchema.parse(readFileSync(getManifestPath(pkgRoot), 'utf-8'))
}

/**
 * Write a route manifest to `scripts/route-baseline/manifest.gen.json` under `pkgRoot`.
 *
 * Validates with Zod before writing so only schema-shaped data is committed.
 *
 * @param manifest - Manifest to serialize
 * @param pkgRoot - UI package root (or a temp directory in tests)
 * @returns Absolute path written
 */
export function writeManifest(manifest: RouteManifest, pkgRoot = getPackageRoot()): string {
  const validated = routeManifestSchema.parse(manifest)
  const path = getManifestPath(pkgRoot)
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, stableStringify(validated), 'utf-8')
  return path
}

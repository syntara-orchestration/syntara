/**
 * Regenerate `scripts/route-baseline/manifest.gen.json` from the current route sources.
 *
 * Usage:
 *   npm run route-baseline:update
 *
 * Writes the manifest and formats it with Prettier. Commit the result in the
 * same PR as the intentional route change. Exits non-zero when AppRoute /
 * navigation parity gaps or unmounted modules remain.
 */

import { updateRouteBaseline } from './run-route-baseline'

try {
  const result = updateRouteBaseline()
  console.log(`Wrote ${result.routeCount} routes to ${result.path}`)
} catch (error) {
  const message = error instanceof Error ? error.message : String(error)
  console.error(message)
  process.exit(1)
}

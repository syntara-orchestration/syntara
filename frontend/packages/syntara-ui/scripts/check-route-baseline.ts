/**
 * Verify the committed route baseline matches a fresh generate.
 *
 * Usage:
 *   npm run route-baseline:check
 *
 * Exit codes:
 *   0 — manifest matches
 *   1 — drift detected (run route-baseline:update if intentional)
 */

import { checkRouteBaseline } from '../src/app/route-baseline/run-route-baseline'

const result = checkRouteBaseline()

if (!result.ok) {
  for (const line of result.messages) {
    console.error(line)
  }
  process.exit(1)
}

console.log(`Route baseline OK (${result.manifest.routes.length} routes)`)

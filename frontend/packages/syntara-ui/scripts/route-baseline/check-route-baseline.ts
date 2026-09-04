/**
 * Compare live route sources to the committed `route-baseline/manifest.gen.json`.
 *
 * Usage:
 *   npm run route-baseline:check
 *
 * Exits non-zero on drift or source-parity gaps. Does not run Vitest —
 * collector unit tests are covered by `npm run vitest` / `npm test`.
 */

import { checkRouteBaseline } from './run-route-baseline'

const result = checkRouteBaseline()
if (result.ok) {
  console.log(`OK: route baseline matches (${result.manifest.routes.length} routes)`)
  process.exit(0)
}

console.error(result.messages.join('\n'))
process.exit(1)

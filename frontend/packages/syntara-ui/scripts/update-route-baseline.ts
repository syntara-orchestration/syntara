/**
 * Regenerate `route-baseline/manifest.json` from the current route sources.
 *
 * Usage:
 *   npm run route-baseline:update
 *
 * Commit the updated manifest in the same PR as the intentional route change.
 */

import { updateRouteBaseline } from '../src/app/route-baseline/run-route-baseline'

const result = updateRouteBaseline()

if (result.appRouteOnly.length > 0) {
  console.warn('AppRoute templates missing from manifest (except known exceptions):')
  for (const template of result.appRouteOnly) console.warn(`  - ${template}`)
}

if (result.navigationOnly.length > 0) {
  console.warn('Navigation templates missing from manifest:')
  for (const template of result.navigationOnly) console.warn(`  - ${template}`)
}

console.log(`Wrote ${result.routeCount} routes to ${result.path}`)

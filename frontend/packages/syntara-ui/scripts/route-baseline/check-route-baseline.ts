/**
 * Compare live route sources to the committed `scripts/route-baseline/manifest.gen.json`.
 *
 * Usage:
 *   npm run route-baseline:check
 *
 * Exits non-zero on drift or source-parity gaps. This is the product contract
 * check (local + CI). Vitest covers collector/update helpers on fixtures —
 * it does not re-assert the live committed manifest.
 */

import { appendFileSync } from 'node:fs'

import { checkRouteBaseline } from './run-route-baseline'

const result = checkRouteBaseline()
if (result.ok) {
  const okLine = `OK: route baseline matches (${result.manifest.routes.length} routes)`
  console.log(okLine)
  writeGitHubSummary(`## Route baseline\n\n${okLine}\n`)
  process.exit(0)
}

const report = result.messages.join('\n')
console.error(report)

if (process.env.GITHUB_ACTIONS === 'true') {
  // Single annotation so the Actions UI points at the contract failure.
  console.error(
    `::error title=Route baseline drift::${escapeGitHubAnnotation(result.messages[0] ?? 'Route baseline check failed')}`
  )
  writeGitHubSummary(['## Route baseline failed', '', '```', report, '```', ''].join('\n'))
}

process.exit(1)

/**
 * Append markdown to the GitHub Actions job summary when running in CI.
 *
 * @param markdown - Summary body to append
 */
function writeGitHubSummary(markdown: string): void {
  const summaryPath = process.env.GITHUB_STEP_SUMMARY
  if (!summaryPath) return
  appendFileSync(summaryPath, `${markdown}\n`, 'utf-8')
}

/**
 * Escape text for a GitHub Actions `::error::` annotation payload.
 *
 * @param text - Raw message line
 * @returns Escaped annotation text
 */
function escapeGitHubAnnotation(text: string): string {
  return text.replace(/%/g, '%25').replace(/\r/g, '%0D').replace(/\n/g, '%0A')
}

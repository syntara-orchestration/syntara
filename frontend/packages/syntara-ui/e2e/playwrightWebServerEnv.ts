/**
 * Real-backend E2E runs set `SYNTARA_E2E_SKIP_WEB_SERVER=1` so Playwright does not start the mock
 * API + UI (`playwright.config.ts` webServer). Visual baseline generation must **not** treat
 * arbitrary non-empty env values as “skip” (org defaults would otherwise skip every snapshot test
 * and `/update-screenshots` would commit nothing).
 *
 * Keep this logic aligned with `playwright.config.ts` and `e2e/visual-regression/page-screenshots.spec.ts`.
 */
export function isSkipWebServerForPlaywrightTests(): boolean {
  const v = process.env.SYNTARA_E2E_SKIP_WEB_SERVER?.toLowerCase().trim() ?? ''
  return v === '1' || v === 'true' || v === 'yes'
}

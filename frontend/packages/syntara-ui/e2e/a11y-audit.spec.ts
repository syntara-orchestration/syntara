/**
 * Full-page accessibility audit across the visual regression page registry.
 *
 * Runs axe-core (WCAG 2.x A/AA) on every entry in `visual-regression/page-registry.ts`
 * and writes a structured violation report. This spec is **reporting only** — tests
 * always pass so CI is not gated on the current violation backlog.
 *
 * Usage:
 *   npm run e2e:a11y-audit
 *   (from frontend/ or packages/syntara-ui/)
 *
 * Output:
 *   - Per-page annotations and JSON attachments in the Playwright report
 *   - Combined report at `test-results/a11y-audit-report.json`
 *   - Summary printed to stdout when the audit completes
 *
 * CI gating promotion plan (not implemented yet):
 *   1. Run this spec locally or in a scheduled workflow until `totalViolations` is 0
 *      (or only accepted exceptions remain).
 *   2. Flip the spec from report-only to enforcement: assert `violationCount === 0`
 *      per page (same pattern as `e2e/accessibility.spec.ts`).
 *   3. Remove `@local-only` and the `isSkipWebServerForPlaywrightTests()` skip so the
 *      suite runs in compose E2E against the real backend, or keep mock-API coverage
 *      in a dedicated job if seed data stays the source of truth for full-page states.
 *   4. Add the spec to the required PR/merge gate (no change until step 2 is done).
 *
 * Requires mock API seed data (same constraint as visual regression screenshots).
 */
import AxeBuilder from '@axe-core/playwright'

import { VISUAL_REGRESSION_CLOCK } from '../playwright.config'
import {
  buildPageReport,
  formatAuditSummary,
  formatPageKey,
  mergeAuditReport,
  type A11yPageReport,
  writeAuditReport,
} from '../scripts/a11y-audit-report'

import { appBaseUrl, expect, test, toAppUrl, type Page } from './fixtures'
import { WCAG_TAGS } from './fixtures/accessibility'
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'
import { loginPages, pages, type PageEntry } from './visual-regression/page-registry'
import { stabilizeReactFlowViewport } from './visual-regression/stabilizeViewport'

const AUDIT_TIMEOUT_MS = 900_000

async function waitForPageReady(page: Page): Promise<void> {
  await expect(page.locator('[class*="skeleton"]'))
    .toHaveCount(0, { timeout: 10_000 })
    .catch(() => {})
  await expect(page.locator('[aria-label="Loading"]'))
    .toHaveCount(0, { timeout: 5_000 })
    .catch(() => {})
}

async function auditPage(page: Page, entry: PageEntry): Promise<A11yPageReport> {
  await page.goto(toAppUrl(entry.path))

  try {
    await entry.waitFor(page)

    if (entry.setup) {
      await entry.setup(page)
    }

    await waitForPageReady(page)
    await stabilizeReactFlowViewport(page)
  } catch (error) {
    const loadError = error instanceof Error ? error.message : String(error)
    return {
      section: entry.section,
      name: entry.name,
      path: entry.path,
      violationCount: 0,
      violations: [],
      loadError,
    }
  }

  const axeResults = await new AxeBuilder({ page }).withTags([...WCAG_TAGS]).analyze()
  return buildPageReport(entry, axeResults)
}

async function attachPageReport(
  pageReport: A11yPageReport,
  testInfo: import('@playwright/test').TestInfo
): Promise<void> {
  if (pageReport.loadError) {
    testInfo.annotations.push({
      type: 'page-load-warning',
      description: `${formatPageKey(pageReport)}: ${pageReport.loadError}`,
    })
  }

  if (pageReport.violationCount > 0) {
    testInfo.annotations.push({
      type: 'a11y-violations',
      description: `${pageReport.violationCount} violation(s) on ${formatPageKey(pageReport)}`,
    })
  }

  await testInfo.attach(`a11y-${pageReport.section}-${pageReport.name}.json`, {
    body: JSON.stringify(pageReport, null, 2),
    contentType: 'application/json',
  })
}

test.describe('A11y audit', { tag: '@local-only' }, () => {
  test.skip(
    isSkipWebServerForPlaywrightTests(),
    'Full-page a11y audit requires mock API seed data; skipped in real-backend E2E runs'
  )

  test('reports axe violations for all page-registry entries', async ({ browser }, testInfo) => {
    test.setTimeout(AUDIT_TIMEOUT_MS)

    const pageReports: A11yPageReport[] = []

    const authenticatedContext = await browser.newContext()
    const authenticatedPage = await authenticatedContext.newPage()
    try {
      await authenticatedPage.goto(appBaseUrl)
      await expect(authenticatedPage.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
      await authenticatedPage.clock.setFixedTime(new Date(VISUAL_REGRESSION_CLOCK))
      await authenticatedPage.evaluate(() => localStorage.removeItem('syntara-selected-project'))

      for (const entry of pages) {
        await authenticatedPage.unrouteAll({ behavior: 'ignoreErrors' })

        if (entry.role) {
          await authenticatedPage.route('**/api/v1/auth/refresh', (route) =>
            route.fulfill({
              status: 200,
              contentType: 'application/json',
              body: JSON.stringify({
                access_token: `mock-token-${entry.role}`,
                token_type: 'bearer',
                expires_in: 3600,
              }),
            })
          )
          await authenticatedPage.goto(appBaseUrl)
          await expect(authenticatedPage.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
          await authenticatedPage.clock.setFixedTime(new Date(VISUAL_REGRESSION_CLOCK))
          await authenticatedPage.evaluate(() => localStorage.removeItem('syntara-selected-project'))
        }

        const pageReport = await auditPage(authenticatedPage, entry)
        pageReports.push(pageReport)
        await attachPageReport(pageReport, testInfo)
      }
    } finally {
      await authenticatedContext.close()
    }

    const loginContext = await browser.newContext({ storageState: { cookies: [], origins: [] } })
    const loginPage = await loginContext.newPage()
    try {
      await loginPage.route('**/api/v1/auth/refresh', (route) =>
        route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Unauthorized"}' })
      )

      for (const entry of loginPages) {
        const pageReport = await auditPage(loginPage, entry)
        pageReports.push(pageReport)
        await attachPageReport(pageReport, testInfo)
      }
    } finally {
      await loginContext.close()
    }

    const report = mergeAuditReport(pageReports)
    const outputPath = await writeAuditReport(report)
    process.stdout.write(`\n${formatAuditSummary(report)}\n`)
    process.stdout.write(`\nA11y audit report written to ${outputPath}\n`)
  })
})

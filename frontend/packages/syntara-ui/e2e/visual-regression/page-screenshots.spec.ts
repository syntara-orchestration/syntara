/**
 * Full-page visual regression tests.
 *
 * Crawls every route in the page registry and takes a deterministic screenshot.
 * Accessibility scanning is handled separately in accessibility.spec.ts.
 *
 * Usage:
 *   Generate baselines:  npx playwright test page-screenshots --update-snapshots
 *   Compare baselines:   npx playwright test page-screenshots
 *
 * NOTE: This spec does NOT use the `app` fixture so that `page.clock` can be
 * set after login, freezing timestamps for deterministic output.
 */
import { expect, test } from '@playwright/test'

import { VISUAL_REGRESSION_CLOCK } from '../../playwright.config'
import { appBaseUrl, toAppUrl } from '../fixtures'
import { isSkipWebServerForPlaywrightTests } from '../playwrightWebServerEnv'

import { brandChromeMasks } from './brandMasks'
import { loginPages, pages } from './page-registry'
import { stabilizeReactFlowViewport } from './stabilizeViewport'

const SCREENSHOT_OPTIONS = {
  maxDiffPixelRatio: 0.005,
  animations: 'disabled' as const,
  fullPage: true,
}

// Neutral grey used to paint over masked regions (React Flow canvas + brand chrome).
// Pink (#FF00FF, Playwright's default) is visually jarring in baseline reviews;
// grey blends with the surrounding UI for easier baseline inspection.
const MASK_COLOR = '#e8e8e8'

// Run tests sequentially but don't stop on failure — critical for first-time
// baseline generation where every test "fails" (no snapshot to compare against)
test.describe.configure({ mode: 'default' })

test.describe('Page screenshots', { tag: '@local-only' }, () => {
  // Baselines require the mock API with known seed data; skip when running
  // against a real backend (the E2E workflow sets SYNTARA_E2E_SKIP_WEB_SERVER=1).
  // The Visual Regression manual workflow uses the mock API, so CI=true
  // alone is not a valid skip condition.
  test.skip(
    isSkipWebServerForPlaywrightTests(),
    'Page screenshot baselines require mock API seed data; skipped in real-backend E2E runs'
  )

  // Canvas pages must declare perceptual: true — this is the signal that the page
  // renders a ReactFlow canvas and should have .react-flow masked in the screenshot.
  // Masking replaces the canvas with a solid rectangle, making comparisons 100%
  // deterministic regardless of ReactFlow rendering or fitView() floating-point output.
  // The surrounding UI chrome (toolbar, panels, breadcrumbs) is still pixel-compared.
  const missingPerceptual = pages.filter((e) => e.section === 'workflows' && !e.perceptual).map((e) => e.name)
  if (missingPerceptual.length > 0) {
    throw new Error(`Workflow entries must have perceptual: true — missing on: ${missingPerceptual.join(', ')}`)
  }

  for (const entry of pages) {
    test(`${entry.section}/${entry.name}`, async ({ page }) => {
      // ReactFlow canvas pages mount considerably more DOM/JS than a typical page and
      // are the most sensitive to CI runner contention (shared runners, concurrent
      // jobs). Give them extra headroom above the global 60s default so a slow but
      // otherwise-healthy render doesn't get reported as a false failure.
      if (entry.perceptual) {
        test.setTimeout(90_000)
      }

      // For role-specific entries, intercept auth to return a role-scoped token
      if (entry.role) {
        await page.route('**/api/v1/auth/refresh', (route) =>
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
      }

      // Login — navigating to the base URL auto-authenticates with the mock API
      await page.goto(appBaseUrl)
      await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()

      await page.clock.setFixedTime(new Date(VISUAL_REGRESSION_CLOCK))

      // Clear persisted project-selector state so every screenshot starts from
      // the same "All projects" baseline regardless of test ordering.
      await page.evaluate(() => localStorage.removeItem('syntara-selected-project'))

      // Navigate to the target page
      await page.goto(toAppUrl(entry.path))

      // Wait for page-specific content to load
      await entry.waitFor(page)

      // Optional setup (e.g., pages needing interaction before screenshot)
      if (entry.setup) {
        await entry.setup(page)
      }

      // Wait for all network requests to settle before taking the screenshot
      await page.waitForLoadState('networkidle')

      // Wait for PatternFly skeleton loaders and spinner elements to clear.
      // Without this, a screenshot taken while data is still loading captures
      // a skeleton/spinner state — future runs then diff against that instead
      // of the real content, creating permanent false positives.
      await expect(page.locator('.pf-v6-c-skeleton'))
        .toHaveCount(0, { timeout: 10_000 })
        .catch(() => {})
      await expect(page.locator('[aria-label="Loading"]'))
        .toHaveCount(0, { timeout: 5_000 })
        .catch(() => {})

      // Belt-and-suspenders: inject CSS to freeze all animations/transitions
      // immediately. This runs before getAnimations() so any animation that
      // started after networkidle is also caught. Complements animations:'disabled'
      // on the screenshot call (which only acts at capture time).
      await page.addStyleTag({
        content: '*, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; }',
      })

      // Wait for any animations still in-flight to finish (belt-and-suspenders;
      // the CSS injection above should stop them within one rAF).
      await page
        .waitForFunction(
          () => document.getAnimations().every((a) => a.playState === 'finished' || a.playState === 'idle'),
          undefined,
          { timeout: 5_000, polling: 'raf' }
        )
        .catch((e: unknown) => {
          // Non-fatal: some pages have indefinitely-running animations (e.g. persistent
          // spinners). Annotate the test so CI surfaces which pages have running
          // animations — aids debugging without blocking the suite.
          const msg = e instanceof Error ? e.message : String(e)
          test.info().annotations.push({
            type: 'warning',
            description: `getAnimations timed out for ${entry.section}/${entry.name}: ${msg}`,
          })
        })

      // Remove focus from any active element to avoid flaky focus-ring diffs
      await page.evaluate(() => {
        if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
      })

      // Snap React Flow viewport to integer pixels (no-op for non-canvas pages).
      // Uses rAF-based polling — deterministic under any CI load level.
      await stabilizeReactFlowViewport(page)

      // Screenshot with section-based directory organization
      const snapshotName = [entry.section, `${entry.name}.png`]
      const brandMasks = await brandChromeMasks(page)
      if (entry.perceptual) {
        // Canvas pages: mask the ReactFlow canvas with a solid rectangle so the
        // comparison is 100% deterministic regardless of node positions, edge routing,
        // or fitView() floating-point output. The surrounding UI chrome (toolbar,
        // side panels, breadcrumbs) is still pixel-compared and catches real regressions.
        // Skip the mask when maskCanvas === false (NodeEditorOverlay step/trigger forms):
        // the overlay shares the canvas bounding box, so masking would erase the form.
        // Per-entry maxDiffPixelRatio overrides are passed through (non-canvas chrome
        // may legitimately need a looser threshold, e.g. animated edge status indicators).
        const maskCanvas = entry.maskCanvas !== false
        const mask = [...brandMasks, ...(maskCanvas ? [page.locator('.react-flow')] : [])]
        const perceptualOptions = {
          ...SCREENSHOT_OPTIONS,
          ...(entry.maxDiffPixelRatio ? { maxDiffPixelRatio: entry.maxDiffPixelRatio } : {}),
          mask,
          maskColor: MASK_COLOR,
        }
        await expect(page).toHaveScreenshot(snapshotName, perceptualOptions)
      } else {
        const options = {
          ...SCREENSHOT_OPTIONS,
          ...(entry.maxDiffPixelRatio ? { maxDiffPixelRatio: entry.maxDiffPixelRatio } : {}),
          mask: brandMasks,
          maskColor: MASK_COLOR,
        }
        await expect(page).toHaveScreenshot(snapshotName, options)
      }
    })
  }
})

test.describe('Login page screenshots', { tag: '@local-only' }, () => {
  test.skip(
    isSkipWebServerForPlaywrightTests(),
    'Login page baselines require mock API seed data; skipped in real-backend E2E runs'
  )

  for (const entry of loginPages) {
    test(`${entry.section}/${entry.name}`, async ({ page }) => {
      // Block token refresh so the app shows the login page instead of auto-authenticating
      await page.route('**/api/v1/auth/refresh', (route) =>
        route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Unauthorized"}' })
      )

      await page.goto(toAppUrl(entry.path))
      await entry.waitFor(page)

      if (entry.setup) {
        await entry.setup(page)
      }

      await page.waitForLoadState('networkidle')

      await page.evaluate(() => {
        if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
      })
      const brandMasks = await brandChromeMasks(page)
      await expect(page).toHaveScreenshot([entry.section, `${entry.name}.png`], {
        ...SCREENSHOT_OPTIONS,
        mask: brandMasks,
        maskColor: MASK_COLOR,
      })
    })
  }
})

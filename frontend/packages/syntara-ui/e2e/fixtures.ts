import { type CurrentsFixtures, type CurrentsWorkerFixtures, fixtures } from '@currents/playwright'
import { expect, test as base, type Page, type Request } from '@playwright/test'

import { APP_TITLE } from './helpers/appTitle'
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'
import { type RoleSetupResult, setupRoleUsers } from './utils/roleSetup'
import {
  type XfailEntry,
  applyQuarantineAfterRun,
  loadXfailEntries,
  matchesXfail,
  xfailSourceFromEnv,
} from './xfailFromUrl'

const processEnv: Record<string, string | undefined> = (
  process as unknown as { env: Record<string, string | undefined> }
).env
export const appBaseUrl: string = processEnv['SYNTARA_E2E_BASE_URL'] ?? 'http://localhost:4173'
const e2ePassword: string | undefined = processEnv['SYNTARA_E2E_PASSWORD']
const isRealBackend: boolean = isSkipWebServerForPlaywrightTests()

export const toAppUrl = (path: string): string => new URL(path, appBaseUrl).toString()

async function loginAs(page: Page, username: string, password?: string): Promise<void> {
  await page.goto(appBaseUrl)

  const loginHeading = page.getByRole('heading', { name: `Log in to ${APP_TITLE}` })
  const mainNav = page.getByRole('navigation', { name: 'Main navigation' })
  await loginHeading.or(mainNav).waitFor({ timeout: 15_000 })

  if (await loginHeading.isVisible()) {
    const pw = password ?? e2ePassword
    if (!pw) {
      throw new Error('Login page detected but no password available')
    }

    const localAccountToggle = page.getByRole('button', { name: 'Sign in using local account' })
    if (await localAccountToggle.isVisible()) {
      await localAccountToggle.click()
    }

    await page.getByLabel('Username').fill(username)
    await page.getByRole('textbox', { name: 'Password' }).fill(pw)
    await page.getByRole('button', { name: /^Log in( as administrator)?$/ }).click()
    await expect(mainNav).toBeVisible()
  }
}

async function loginAsRole(page: Page, username: string): Promise<void> {
  // Intercept auth refresh to return a token for this role.
  // The mock API's cookie-based bootstrap refresh would otherwise return
  // an admin token, preventing the role-specific flow.
  await page.route('**/api/v1/auth/refresh', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: `mock-token-${username}`,
        token_type: 'bearer',
        expires_in: 3600,
      }),
    })
  )

  await page.goto(appBaseUrl)
  await page.getByRole('navigation', { name: 'Main navigation' }).waitFor({ timeout: 15_000 })
}

// Currents action fixtures (flaky test quarantine) must be applied to the base
// before our project fixtures extend it. Tests run inside a Podman container in CI,
// so there is no host-side pre-step that can inject a quarantine list — the fixture
// mechanism is the only approach that works within the container's Playwright process.
const currentsBase = base.extend<CurrentsFixtures, CurrentsWorkerFixtures>({
  ...fixtures.baseFixtures,
  ...fixtures.actionFixtures,
})

const xfailBase = currentsBase.extend<{ _xfailCheck: void }, { _xfailEntries: XfailEntry[] }>({
  _xfailEntries: [
    async ({}, use) => {
      const source = xfailSourceFromEnv(processEnv)
      if (!source) {
        await use([])
        return
      }
      const entries = await loadXfailEntries(source)
      if (entries.length > 0) {
        process.stderr.write(`xfail: loaded ${entries.length} pattern(s) from ${source}\n`)
      }
      await use(entries)
    },
    { scope: 'worker' },
  ],
  _xfailCheck: [
    async ({ _xfailEntries }, use, testInfo) => {
      // Match before the test so titlePath is complete; apply quarantine after
      // so a listed failure is skipped (Currents-style) and a listed pass is
      // left as a pass rather than Playwright "Expected to fail, but passed".
      const match = matchesXfail(testInfo, _xfailEntries)
      await use()
      applyQuarantineAfterRun(testInfo, match)
    },
    { auto: true },
  ],
})

export const test = xfailBase.extend<
  { app: Page; auditorApp: Page; viewerApp: Page; userApp: Page; projectAdminApp: Page },
  { roleSetup: RoleSetupResult | null }
>({
  // Worker-scoped: create role users once per worker on real backend.
  // On mock API this is null and the fixtures fall back to mock-token interception.
  roleSetup: [
    async ({ playwright }, use) => {
      if (!isRealBackend) {
        await use(null)
        return
      }
      const request = await playwright.request.newContext()
      const setup = await setupRoleUsers(request)
      await use(setup)
      await setup.cleanup()
      await request.dispose()
    },
    { scope: 'worker' },
  ],

  app: async ({ page }, use) => {
    await loginAs(page, 'admin')
    await use(page)
  },

  auditorApp: async ({ browser, roleSetup }, use) => {
    const context = await browser.newContext()
    const page = await context.newPage()
    if (roleSetup) {
      const { username, password } = roleSetup.credentials.auditor
      await loginAs(page, username, password)
    } else {
      await loginAsRole(page, 'auditor')
    }
    await use(page)
    await context.close()
  },

  viewerApp: async ({ browser, roleSetup }, use) => {
    const context = await browser.newContext()
    const page = await context.newPage()
    if (roleSetup) {
      const { username, password } = roleSetup.credentials.viewer
      await loginAs(page, username, password)
    } else {
      await loginAsRole(page, 'viewer')
    }
    await use(page)
    await context.close()
  },

  userApp: async ({ browser, roleSetup }, use) => {
    const context = await browser.newContext()
    const page = await context.newPage()
    if (roleSetup) {
      const { username, password } = roleSetup.credentials.user
      await loginAs(page, username, password)
    } else {
      await loginAsRole(page, 'user')
    }
    await use(page)
    await context.close()
  },

  // Mock-only — no roleSetup support; real-backend tests skip via isRealBackend guard in spec files
  projectAdminApp: async ({ browser }, use) => {
    const context = await browser.newContext()
    const page = await context.newPage()
    await loginAsRole(page, 'project-admin')
    await use(page)
    await context.close()
  },
})

/**
 * Creates a describe-scoped guard that skips all remaining tests without
 * setting up fixtures once a data-availability check fails.
 *
 * Configures the enclosing describe as `mode: 'serial'` so the unavailable
 * flag reliably propagates across tests (with `fullyParallel: true`, parallel
 * tests land on separate workers that each have their own flag).
 *
 * Usage inside a test.describe:
 *   const guard = createUnavailableGuard('No data available')
 *   test.beforeEach(async ({ app }) => {
 *     const hasData = await checkData(app)
 *     if (!hasData) guard.markUnavailable()
 *     test.skip(!hasData, 'No data available')
 *   })
 */
export function createUnavailableGuard(reason: string) {
  let unavailable = false
  test.describe.configure({ mode: 'serial' })
  test.beforeEach(() => {
    test.skip(unavailable, reason)
  })
  return {
    markUnavailable: () => {
      unavailable = true
    },
  }
}

export { expect, type Page, type Request }

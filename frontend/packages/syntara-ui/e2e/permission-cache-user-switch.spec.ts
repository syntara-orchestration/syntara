/**
 * E2E Tests: Permission cache invalidation on user switch (AAP-77299)
 *
 * After logout and re-login as a lower-privilege user, permission-gated nav
 * items must reflect the new user's permissions without a hard refresh.
 *
 * Root cause: useCanI / usePermissionChecks use staleTime: Infinity. Without
 * queryClient.clear() on logout, the previous user's cached permissions survive
 * the session boundary and are served to the next user.
 */

import { type Page } from '@playwright/test'

import { test, expect, toAppUrl } from './fixtures'
import { APP_TITLE } from './helpers/appTitle'
import { buildUniqueName } from './helpers/workflows'

const VIEWER_PASSWORD = 'e2e-test-password-123!'

async function fillLoginForm(page: Page, username: string, password: string): Promise<void> {
  const localAccountToggle = page.getByRole('button', { name: 'Sign in using local account' })
  if (await localAccountToggle.isVisible()) await localAccountToggle.click()
  await page.getByLabel('Username').fill(username)
  await page.getByRole('textbox', { name: 'Password' }).fill(password)
  await page.getByRole('button', { name: /^Log in( as administrator)?$/ }).click()
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
}

test('switching users reflects new permissions without hard refresh', async ({ page }) => {
  const adminPassword = process.env.SYNTARA_E2E_PASSWORD
  // SYNTARA_E2E_SKIP_WEB_SERVER=1 is the project-wide signal for real-backend runs.
  const isRealBackend = !!process.env.SYNTARA_E2E_SKIP_WEB_SERVER

  const viewerUsername = buildUniqueName('e2e-perm-viewer')
  let viewerId: string | null = null

  try {
    if (isRealBackend) {
      if (!adminPassword) throw new Error('SYNTARA_E2E_PASSWORD must be set when running against the real backend')

      // Call the backend directly rather than through the UI proxy to avoid
      // stale proxy config from a previously-started dev server.
      const backendUrl = process.env.VITE_API_URL ?? process.env.SYNTARA_E2E_BASE_URL ?? 'http://localhost:8000'

      const tokenResp = await page.request.post(`${backendUrl}/api/v1/auth/login`, {
        data: { username: 'admin', password: adminPassword },
      })
      expect(tokenResp.ok(), `admin login failed: ${tokenResp.status()}`).toBeTruthy()
      const { access_token: token } = (await tokenResp.json()) as { access_token: string }

      // Newly created users belong only to the "authenticated" built-in group,
      // which has no access to System Administration.
      const createResp = await page.request.post(`${backendUrl}/api/v1/users`, {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          username: viewerUsername,
          email: `${viewerUsername}@example.com`,
          first_name: 'E2E Viewer',
          password: VIEWER_PASSWORD,
        },
      })
      expect(createResp.ok(), `viewer user creation failed: ${createResp.status()}`).toBeTruthy()
      viewerId = ((await createResp.json()) as { id: string }).id

      // The login call above sets the admin session cookie in the browser context.
      await page.goto(toAppUrl('/'))
      await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible({ timeout: 15_000 })

      await expect(page.getByRole('button', { name: 'System Administration' })).toBeVisible({ timeout: 15_000 })
      await expect(page.getByRole('link', { name: 'Workflows' })).toBeVisible()

      await page.getByRole('button', { name: 'User menu' }).click()
      await page.getByRole('menuitem', { name: 'Logout' }).click()

      // Log in as viewer within the same SPA session — page.goto() would always
      // clear the cache via a full React remount, which would hide any regression.
      await page.getByRole('heading', { name: `Log in to ${APP_TITLE}` }).waitFor({ timeout: 15_000 })
      await fillLoginForm(page, viewerUsername, VIEWER_PASSWORD)
    } else {
      // Mock API tokens encode the username as mock-token-{username}, so the UI
      // can be bootstrapped for any role by intercepting the refresh endpoint.
      let currentUser = 'admin'
      await page.route('**/api/v1/auth/refresh', (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ access_token: `mock-token-${currentUser}`, token_type: 'bearer', expires_in: 3600 }),
        })
      )

      await page.goto(toAppUrl('/'))
      await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
      await expect(page.getByRole('button', { name: 'System Administration' })).toBeVisible({ timeout: 15_000 })
      await expect(page.getByRole('link', { name: 'Workflows' })).toBeVisible()

      currentUser = 'viewer'
      await page.route('**/api/v1/auth/logout*', (route) => route.fulfill({ status: 204, body: '' }))
      await page.getByRole('button', { name: 'User menu' }).click()
      await page.getByRole('menuitem', { name: 'Logout' }).click()
      await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
    }

    // If the cache was not cleared on logout, the admin-cached permission would
    // incorrectly show System Administration to the viewer.
    await expect(page.getByRole('button', { name: 'System Administration' })).not.toBeVisible()
    await expect(page.getByRole('link', { name: 'Workflows' })).toBeVisible()
  } finally {
    if (viewerId) {
      const backendUrl = process.env.VITE_API_URL ?? process.env.SYNTARA_E2E_BASE_URL ?? 'http://localhost:8000'
      const tokenResp = await page.request.post(`${backendUrl}/api/v1/auth/login`, {
        data: { username: 'admin', password: adminPassword },
      })
      if (tokenResp.ok()) {
        const { access_token: token } = (await tokenResp.json()) as { access_token: string }
        await page.request.delete(`${backendUrl}/api/v1/users/${viewerId}`, {
          headers: { Authorization: `Bearer ${token}` },
        })
      }
    }
  }
})

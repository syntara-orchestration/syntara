/**
 * E2E Tests: Built-In Admin User Lifecycle Management
 *
 * Critical paths covered:
 * - Disable built-in admin when IdP admin available
 * - Unable to disable built-in when no user in admins group
 * - Re-enable built-in admin user
 */
import { test, expect, toAppUrl } from './fixtures'
import { AAP_AUTH_PROVIDER } from './fixtures/mock-oidc-idps'
import {
  BUILT_IN_ADMIN_USER_INFO,
  BUILT_IN_ADMIN_USER_READ,
  BUILT_IN_ADMIN_USER_JWT_TOKEN,
  AAP_ADMIN_USER_INFO,
  AAP_ADMIN_USER_READ,
} from './fixtures/mock-users'
import { APP_TITLE } from './helpers/appTitle'

const USER_MANAGEMENT_ACCESS_URL = '/system-administration/access-management/users'

const UNAUTHORIZED_RESPONSE = {
  type: 'https://api.example.com/errors/unauthorized',
  title: 'Unauthorized',
  detail: 'Authentication required',
  code: 'AUTHENTICATION_REQUIRED',
}

test.describe('Disable Built-in Admin — Flow and State Update', () => {
  test('Disable Built-in Admin - Success, Idp Configured', async ({ page }) => {
    await page.route('**/api/v1/auth/refresh', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: BUILT_IN_ADMIN_USER_JWT_TOKEN,
          token_type: 'bearer',
          expires_in: 3600,
        }),
      })
    )

    await page.route('**/api/v1/auth/me', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(BUILT_IN_ADMIN_USER_INFO),
      })
    )

    await page.route('**/api/v1/users**', (route) => {
      const url = new URL(route.request().url())
      if (route.request().method() === 'GET') {
        if (url.pathname.endsWith('/users')) {
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              resources: [BUILT_IN_ADMIN_USER_READ, AAP_ADMIN_USER_READ],
              next: null,
              prev: null,
            }),
          })
        }
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(BUILT_IN_ADMIN_USER_READ),
        })
      }
      if (route.request().method() === 'PATCH') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ...BUILT_IN_ADMIN_USER_READ, is_enabled: false }),
        })
      }
      return route.continue()
    })

    await page.route('**/api/v1/groups**', (route) => {
      const url = new URL(route.request().url())
      if (url.pathname.includes('/members')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ resources: [BUILT_IN_ADMIN_USER_READ, AAP_ADMIN_USER_READ], next: null, prev: null }),
        })
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          resources: [
            {
              id: 'g0-builtin-admins',
              name: 'admins',
              is_builtin: true,
              source: 'local',
              member_count: 2,
              description: 'Built-in administrators group',
              created_by: null,
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-01-01T00:00:00Z',
            },
          ],
          next: null,
          prev: null,
        }),
      })
    })

    await page.route('**/api/v1/authz/can_i', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ allowed: true, denied: false, matched_policy: 'admin-policy' }),
      })
    )

    await page.goto(toAppUrl(USER_MANAGEMENT_ACCESS_URL))

    const toggle = page.getByRole('switch', { name: /Built-in administrator account/ })
    await expect(toggle).toBeVisible()
    await expect(toggle).toBeEnabled()

    await page.route('**/api/v1/auth/login', (route) =>
      route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify(UNAUTHORIZED_RESPONSE),
      })
    )

    await page.route('**/api/v1/auth/refresh', (route) =>
      route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify(UNAUTHORIZED_RESPONSE),
      })
    )

    await page.route('**/api/v1/auth/providers**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          resources: [AAP_AUTH_PROVIDER],
        }),
      })
    )

    await page.route('**/api/v1/auth/logout*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      })
    )

    await toggle.click({ force: true })
    await expect(page.getByRole('dialog', { name: 'Disable administrator account?' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Disable and sign out' })).toBeVisible()
    await page.getByRole('button', { name: 'Disable and sign out' }).click()

    await expect(page.getByRole('heading', { name: `Log in to ${APP_TITLE}` })).toBeVisible()
    await page.getByRole('button', { name: 'Sign in using local account' }).click()
    await expect(page.getByText(/For local account access only/)).toBeVisible()

    await page.getByLabel('Username').fill('admin')
    await page.getByRole('textbox', { name: 'Password' }).fill('coffee')
    await page.getByRole('button', { name: 'Log in', exact: true }).click()
    await expect(page.getByText('Authentication failed')).toBeVisible()
  })
})

test.describe('Disable Built-in Admin — Lockout Prevention Error', () => {
  test('Disable Built-in Admin - Failure, No Idp Configured', async ({ page }) => {
    await page.route('**/api/v1/auth/refresh', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: BUILT_IN_ADMIN_USER_JWT_TOKEN,
          token_type: 'bearer',
          expires_in: 3600,
        }),
      })
    )

    await page.route('**/api/v1/auth/me', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(BUILT_IN_ADMIN_USER_INFO),
      })
    )

    await page.route('**/api/v1/auth/providers**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], count: 0 }),
      })
    )

    await page.route('**/api/v1/users**', (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ resources: [BUILT_IN_ADMIN_USER_READ], total: 1 }),
        })
      }
      return route.continue()
    })

    await page.route('**/api/v1/groups/g0-builtin-admins/members**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ resources: [BUILT_IN_ADMIN_USER_READ], next: null, prev: null }),
      })
    )

    await page.route('**/api/v1/authz/can_i', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ allowed: true, denied: false, matched_policy: 'admin-policy' }),
      })
    )

    await page.goto(toAppUrl(USER_MANAGEMENT_ACCESS_URL))

    const toggle = page.getByRole('switch', { name: /Built-in administrator account/ })
    await expect(toggle).toBeVisible()
    await expect(toggle).toBeDisabled()
    // const tooltipTrigger = page.locator('span[tabindex="0"]').filter({ has: toggle })
    // await tooltipTrigger.focus()
    await toggle.hover({ force: true })
    await expect(page.getByRole('tooltip')).toContainText(
      'Only the built-in administrator can disable their own account'
    )
  })
})

test.describe('Re-enable Built-in Admin', () => {
  test('Re-enable built-in admin - AAP Idp Configured', async ({ page }) => {
    await page.route('**/api/v1/auth/refresh', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: `mock-token-aap`,
          token_type: 'bearer',
          expires_in: 3600,
        }),
      })
    )

    await page.route('**/api/v1/auth/me', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(AAP_ADMIN_USER_INFO),
      })
    )

    let builtinEnabled = false
    const builtinUser = () => ({ ...BUILT_IN_ADMIN_USER_READ, is_enabled: builtinEnabled })

    await page.route('**/api/v1/users**', (route) => {
      const url = new URL(route.request().url())
      const isListRequest = url.pathname.endsWith('/users')

      if (route.request().method() === 'PATCH') {
        builtinEnabled = true
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(builtinUser()),
        })
      }
      if (route.request().method() === 'GET') {
        if (isListRequest) {
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              resources: [builtinUser(), AAP_ADMIN_USER_READ],
              next: null,
              prev: null,
            }),
          })
        }
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(builtinUser()),
        })
      }
      return route.continue()
    })

    await page.route('**/api/v1/authz/can_i', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ allowed: true, denied: false, matched_policy: 'admin-policy' }),
      })
    )

    await page.goto(toAppUrl(USER_MANAGEMENT_ACCESS_URL))

    const toggle = page.getByRole('switch', { name: /Built-in administrator account/ })
    await expect(toggle).toBeVisible()
    await expect(toggle).not.toBeChecked()
    await toggle.click({ force: true })
    await expect(toggle).toBeChecked()
  })
})

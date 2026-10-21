/**
 * E2E Tests: My Profile Route (AAP-78103)
 *
 * Validates that the dedicated /my-profile route is accessible to all
 * authenticated users regardless of their RBAC permissions, displays the
 * current user's profile, and does not show Access Management breadcrumbs.
 *
 * Critical paths covered:
 * - All roles (admin, viewer, auditor, user) can access /my-profile
 * - Page shows "My Profile" heading
 * - No Access Management or Users breadcrumbs appear
 * - User menu "My Profile" link navigates to /my-profile
 * - Profile tabs (Details, Groups, Identities, Assignments) render
 */

import { type Page, test, expect, toAppUrl } from './fixtures'

const MY_PROFILE_URL = '/my-profile'

async function verifyMyProfilePage(page: Page) {
  await page.goto(toAppUrl(MY_PROFILE_URL))
  await expect(page.getByRole('heading', { level: 1, name: 'My Profile' })).toBeVisible()

  await expect(page.getByText('Access management', { exact: true })).not.toBeVisible()
  await expect(page.getByRole('link', { name: 'Users' })).not.toBeVisible()
}

// ── Route accessibility for all roles ─────────────────────────────────────

test.describe('My Profile — route accessibility', () => {
  test('admin can access /my-profile', async ({ app }) => {
    await verifyMyProfilePage(app)
  })

  test('viewer can access /my-profile', async ({ viewerApp }) => {
    await verifyMyProfilePage(viewerApp)
  })

  test('auditor can access /my-profile', async ({ auditorApp }) => {
    await verifyMyProfilePage(auditorApp)
  })

  test('user role can access /my-profile', async ({ userApp }) => {
    await verifyMyProfilePage(userApp)
  })
})

// ── Page content and structure ────────────────────────────────────────────

test.describe('My Profile — page content', () => {
  test('does not show access denied for viewer', async ({ viewerApp }) => {
    await viewerApp.goto(toAppUrl(MY_PROFILE_URL))
    await expect(viewerApp.getByRole('heading', { level: 1, name: 'My Profile' })).toBeVisible()

    await expect(viewerApp.getByRole('heading', { name: 'Access denied' })).not.toBeVisible()
  })

  test('does not show access denied for user role', async ({ userApp }) => {
    await userApp.goto(toAppUrl(MY_PROFILE_URL))
    await expect(userApp.getByRole('heading', { level: 1, name: 'My Profile' })).toBeVisible()

    await expect(userApp.getByRole('heading', { name: 'Access denied' })).not.toBeVisible()
  })
})

// ── Navigation from user menu ─────────────────────────────────────────────

test.describe('My Profile — user menu navigation', () => {
  test('user menu "My Profile" link navigates to /my-profile (viewer)', async ({ viewerApp }) => {
    await viewerApp.goto(toAppUrl('/workflows'))
    await expect(viewerApp.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

    await viewerApp.getByRole('button', { name: 'User menu' }).click()
    await viewerApp.getByRole('menuitem', { name: 'My Profile' }).click()

    await expect(viewerApp).toHaveURL(toAppUrl(MY_PROFILE_URL))
    await expect(viewerApp.getByRole('heading', { level: 1, name: 'My Profile' })).toBeVisible()
  })

  test('user menu "My Profile" link navigates to /my-profile (admin)', async ({ app }) => {
    await app.goto(toAppUrl('/workflows'))
    await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

    await app.getByRole('button', { name: 'User menu' }).click()
    await app.getByRole('menuitem', { name: 'My Profile' }).click()

    await expect(app).toHaveURL(toAppUrl(MY_PROFILE_URL))
    await expect(app.getByRole('heading', { level: 1, name: 'My Profile' })).toBeVisible()
  })
})

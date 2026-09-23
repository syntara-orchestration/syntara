/**
 * E2E Tests: Credential Detail Page — Edge Cases (additive)
 *
 * Tests 20 and 26 from the ANSTRAT-1901 test plan. Tests 16-19 (detail page
 * navigation, tabs, metadata, edit modal) are covered by credential-detail.spec.ts.
 * Tests 21-25 (enable/disable flows) are covered by credential-enable-disable.spec.ts.
 *
 * Covers:
 * - Invalid credential ID error state
 * - Workflow fetch error handling in disable dialog
 */

import { test, expect, toAppUrl } from './fixtures'
import { createTestCredential, deleteCredentialByName, navigateToCredentialDetail } from './helpers/credentials'

// ---------------------------------------------------------------------------
// Test 20: Invalid Credential ID
// ---------------------------------------------------------------------------

test.describe('Credential Detail Edge Cases', () => {
  test('invalid credential ID shows error state', async ({ app }) => {
    await app.goto(toAppUrl('/configuration/credentials/00000000-0000-0000-0000-000000000000'))
    await expect(
      app.getByRole('heading', { level: 2, name: /Error loading credential|Invalid credential/ })
    ).toBeVisible({ timeout: 15_000 })
  })

  // ---------------------------------------------------------------------------
  // Test 26: Workflow Fetch Error in Disable Dialog
  // ---------------------------------------------------------------------------

  test('workflow fetch error in disable dialog shows warning', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-t26-error' })
    try {
      await app.route('**/api/v1/credentials/*/workflows', (route) =>
        route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Internal server error' }),
        })
      )

      await navigateToCredentialDetail(app, name)
      await app.getByRole('switch', { name: /enabled/i }).click({ force: true })

      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByText('Disable credential?')).toBeVisible()
      await expect(dialog.getByText(/Unable to check which workflows use this credential/)).toBeVisible()

      await expect(dialog.getByRole('button', { name: 'Disable credential' })).toBeVisible()
      await expect(dialog.getByRole('button', { name: 'Disable credential' })).toBeEnabled()
    } finally {
      await app.unroute('**/api/v1/credentials/*/workflows')
      await deleteCredentialByName(app, name)
    }
  })
})

// ---------------------------------------------------------------------------
// Test 27: Integration Fetch Error in Disable Dialog
// ---------------------------------------------------------------------------

test('integration fetch error in disable dialog shows warning', async ({ app }) => {
  const { name } = await createTestCredential(app, { prefix: 'e2e-int-error' })
  try {
    await app.route('**/api/v1/integrations*', (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Internal server error' }),
      })
    )

    await navigateToCredentialDetail(app, name)
    await app.getByRole('switch', { name: /enabled/i }).click({ force: true })

    const dialog = app.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText('Disable credential?')).toBeVisible()
    await expect(dialog.getByText(/Unable to check which integrations use this credential/)).toBeVisible()

    await expect(dialog.getByRole('button', { name: 'Disable credential' })).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Disable credential' })).toBeEnabled()
  } finally {
    await app.unroute('**/api/v1/integrations*')
    await deleteCredentialByName(app, name)
  }
})

/**
 * E2E Tests: Session Revocation (UI-28, UI-29, UI-30)
 *
 * Critical paths covered:
 * - UI-28: User-scoped session revocation via kebab menu on users table
 * - UI-29: IdP-scoped session revocation via identity provider delete confirmation
 * - UI-30: Global session revocation via Token Revocation tab
 *
 * Reference: ANSTRAT-1844, AAP-71181
 */
import { type Page } from './fixtures'
import { test, expect, toAppUrl } from './fixtures'
import { MINIMAL_OIDC_PROVIDER_CONFIGURATION } from './helpers/identity-providers'
import { buildUniqueName } from './helpers/workflows'
import { createIdentityProviderViaApi, deleteIdentityProviderViaApi } from './utils/api'
import { fulfill, mockCanIAllowed, mockUsersForRevocation, revokeTargetUserResponse } from './utils/mockData'

const AUTHENTICATION_URL = '/system-administration/authentication'
const USERS_URL = '/system-administration/access-management/users'
const TOKEN_REVOCATION_URL = '/system-administration/access-management/token-revocation'

const IDP_DELETE_ACK_LABEL =
  /I understand this identity provider and its linked identities will be permanently deleted/i

async function openDeleteDialogFromList(app: Page, providerName: string) {
  await app.goto(toAppUrl(AUTHENTICATION_URL))
  await expect(app.getByRole('heading', { level: 1, name: 'Identity Providers' })).toBeVisible()

  const table = app.getByRole('grid', { name: 'Identity providers table' })
  await expect(table).toBeVisible()

  const providerRow = table.getByRole('row', { name: new RegExp(providerName) })
  await expect(providerRow).toBeVisible()

  await providerRow.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })
  await app.getByRole('menuitem', { name: 'Delete' }).click()
}

async function confirmIdpDeleteDialog(app: Page, providerName: string) {
  const dialog = app.getByRole('dialog', { name: 'Delete identity provider?' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByText(new RegExp(providerName))).toBeVisible()
  await expect(dialog.getByText(/Revoke active sessions authenticated via this provider/i)).toBeVisible()
  await expect(dialog.getByText(/Remove all user identities linked to this provider/i)).toBeVisible()

  const deleteButton = dialog.getByRole('button', { name: 'Delete' })
  await expect(deleteButton).toBeDisabled()

  const checkbox = dialog.getByRole('checkbox')
  await expect(checkbox).toBeVisible()
  await expect(dialog.getByText(IDP_DELETE_ACK_LABEL)).toBeVisible()
  await checkbox.click()
  await expect(deleteButton).toBeEnabled()
  await deleteButton.click()
}

async function openRevokeDialogForUser(app: Page) {
  await app.goto(toAppUrl(USERS_URL))
  await expect(app.getByRole('heading', { level: 1, name: 'Access Management' })).toBeVisible()

  const userRow = app.getByRole('row', { name: new RegExp(revokeTargetUserResponse.username) })
  await expect(userRow).toBeVisible()

  await userRow.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })
  await app.getByRole('menuitem', { name: 'Revoke tokens' }).click()

  const dialog = app.getByRole('dialog', { name: 'Revoke user tokens?' })
  await expect(dialog).toBeVisible()
  return dialog
}

async function openGlobalRevokeDialog(app: Page) {
  await app.goto(toAppUrl(TOKEN_REVOCATION_URL))
  await expect(app.getByRole('heading', { level: 1, name: 'Access Management' })).toBeVisible()
  await app.getByRole('button', { name: 'Revoke all tokens' }).click()

  const dialog = app.getByRole('dialog', { name: 'Revoke all tokens?' })
  await expect(dialog).toBeVisible()
  return dialog
}

test.describe('Session Revocation — User-Scoped (UI-28)', () => {
  test.beforeEach(async ({ app }) => {
    await mockCanIAllowed(app)
  })

  test('revoke tokens for a specific user via kebab menu shows confirmation and succeeds', async ({ app }) => {
    await mockUsersForRevocation(app)

    await app.route('**/api/v1/admin/revocation/users/**', (route) =>
      route.fulfill(fulfill({ message: `Tokens for user "${revokeTargetUserResponse.username}" have been revoked.` }))
    )

    const dialog = await openRevokeDialogForUser(app)
    await expect(dialog.getByText(revokeTargetUserResponse.username)).toBeVisible()
    await expect(dialog.getByText(/will be revoked/i)).toBeVisible()
    await expect(dialog.getByText(/signed out and must sign in again/i)).toBeVisible()

    const revocationRequest = app.waitForRequest('**/api/v1/admin/revocation/users/**')
    await dialog.getByRole('button', { name: 'Revoke tokens' }).click()

    await expect(app.getByRole('heading', { name: 'Success alert: Tokens revoked' })).toBeVisible({ timeout: 10_000 })
    await expect(
      app.getByText(new RegExp(`Tokens for user "${revokeTargetUserResponse.username}" have been revoked`))
    ).toBeVisible()
    await revocationRequest
  })

  test('revoke tokens dialog can be cancelled without side effects', async ({ app }) => {
    await mockUsersForRevocation(app)

    const dialog = await openRevokeDialogForUser(app)

    await dialog.getByRole('button', { name: 'Cancel' }).click()
    await expect(dialog).not.toBeVisible()

    const userRow = app.getByRole('row', { name: new RegExp(revokeTargetUserResponse.username) })
    await expect(userRow).toBeVisible()
  })

  test('shows error alert when user-scoped revocation API fails', async ({ app }) => {
    await mockUsersForRevocation(app)

    await app.route('**/api/v1/admin/revocation/users/**', (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          type: 'about:blank',
          title: 'Internal Server Error',
          status: 500,
          detail: 'Unexpected error',
        }),
      })
    )

    const dialog = await openRevokeDialogForUser(app)
    await dialog.getByRole('button', { name: 'Revoke tokens' }).click()

    await expect(app.getByRole('heading', { name: /Failed to revoke tokens/i })).toBeVisible({ timeout: 10_000 })
    await expect(dialog).not.toBeVisible()
  })
})

test.describe('Session Revocation — IdP-Scoped (UI-29)', () => {
  test('delete identity provider from list confirms session revocation scope and succeeds', async ({ app }) => {
    const providerName = buildUniqueName('e2e-idp-revoke-sessions')
    let providerId: string | null = null

    try {
      const provider = await createIdentityProviderViaApi(app, {
        name: providerName,
        configuration: MINIMAL_OIDC_PROVIDER_CONFIGURATION,
      })
      providerId = provider?.id ?? null
      expect(providerId).toBeTruthy()

      await openDeleteDialogFromList(app, providerName)
      await confirmIdpDeleteDialog(app, providerName)

      await expect(app.getByRole('heading', { name: 'Identity provider deleted' })).toBeVisible({ timeout: 10_000 })

      const table = app.getByRole('grid', { name: 'Identity providers table' })
      await expect(table.getByRole('row', { name: new RegExp(providerName) })).toHaveCount(0)

      providerId = null
    } finally {
      if (providerId) {
        await deleteIdentityProviderViaApi(app, providerId)
      }
    }
  })

  test('delete identity provider from detail page confirms session revocation scope and succeeds', async ({ app }) => {
    const providerName = buildUniqueName('e2e-idp-revoke-detail')
    let providerId: string | null = null

    try {
      const provider = await createIdentityProviderViaApi(app, {
        name: providerName,
        configuration: MINIMAL_OIDC_PROVIDER_CONFIGURATION,
      })
      providerId = provider?.id ?? null
      expect(providerId).toBeTruthy()

      await app.goto(toAppUrl(`${AUTHENTICATION_URL}/identity-providers/${providerId}`))
      await expect(app.getByRole('heading', { level: 1, name: providerName })).toBeVisible()

      await app.getByRole('button', { name: 'Identity provider actions' }).click()
      await app.getByRole('menuitem', { name: 'Delete identity provider' }).click()

      await confirmIdpDeleteDialog(app, providerName)

      await expect(app.getByRole('heading', { name: 'Identity provider deleted' })).toBeVisible({ timeout: 10_000 })
      await expect(app).toHaveURL(new RegExp(`${AUTHENTICATION_URL.replace(/\//g, '\\/')}$`))

      providerId = null
    } finally {
      if (providerId) {
        await deleteIdentityProviderViaApi(app, providerId)
      }
    }
  })
})

test.describe('Session Revocation — Global (UI-30)', () => {
  test.beforeEach(async ({ app }) => {
    await mockCanIAllowed(app)
  })

  test('global revocation page displays revocation status and revoke button', async ({ app }) => {
    await app.goto(toAppUrl(TOKEN_REVOCATION_URL))

    // Verify status display
    await expect(app.getByText('Tokens revoked before')).toBeVisible()
    await expect(app.getByText('Last updated')).toBeVisible()

    // Verify descriptive text
    await expect(
      app.getByText(/Revoking all tokens will immediately invalidate every active session across the platform/i)
    ).toBeVisible()

    // Verify the danger button is present and enabled
    const revokeButton = app.getByRole('button', { name: 'Revoke all tokens' })
    await expect(revokeButton).toBeVisible()
    await expect(revokeButton).toBeEnabled()
  })

  test('global revocation confirmation dialog warns about scope and requires checkbox acknowledgement', async ({
    app,
  }) => {
    const dialog = await openGlobalRevokeDialog(app)

    await expect(dialog.getByText(/immediately invalidate every active session across the platform/i)).toBeVisible()
    await expect(dialog.getByText(/You will be signed out and must sign in again/i)).toBeVisible()

    const confirmButton = dialog.getByRole('button', { name: 'Revoke all tokens' })
    await expect(confirmButton).toBeDisabled()

    const checkbox = dialog.getByRole('checkbox', {
      name: /I understand all users will be signed out immediately/i,
    })
    await expect(checkbox).toBeVisible()
    await checkbox.click()
    await expect(confirmButton).toBeEnabled()
  })

  test('global revocation confirmation dialog can be cancelled', async ({ app }) => {
    const dialog = await openGlobalRevokeDialog(app)

    await dialog.getByRole('button', { name: 'Cancel' }).click()
    await expect(dialog).not.toBeVisible()

    await expect(app.getByRole('button', { name: 'Revoke all tokens' })).toBeVisible()
  })

  test('global revocation succeeds and triggers logout', async ({ app }) => {
    await app.route('**/api/v1/admin/revocation', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill(fulfill({ message: 'All tokens have been revoked.' }))
      } else {
        await route.continue()
      }
    })
    await app.route('**/api/v1/auth/logout', (route) => route.fulfill(fulfill({})))

    const dialog = await openGlobalRevokeDialog(app)

    const checkbox = dialog.getByRole('checkbox', {
      name: /I understand all users will be signed out immediately/i,
    })
    await checkbox.click()

    const revocationRequest = app.waitForRequest(
      (req) => req.url().includes('/api/v1/admin/revocation') && req.method() === 'POST'
    )
    await dialog.getByRole('button', { name: 'Revoke all tokens' }).click()

    await expect(app.getByRole('heading', { name: 'Success alert: Tokens revoked' })).toBeVisible({ timeout: 10_000 })
    await expect(app.getByText(/All tokens have been revoked/i)).toBeVisible()

    await revocationRequest
  })

  test('shows error alert when global revocation API fails', async ({ app }) => {
    await app.route('**/api/v1/admin/revocation', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({
            type: 'about:blank',
            title: 'Internal Server Error',
            status: 500,
            detail: 'Unexpected error',
          }),
        })
      } else {
        await route.continue()
      }
    })

    const dialog = await openGlobalRevokeDialog(app)

    const checkbox = dialog.getByRole('checkbox', {
      name: /I understand all users will be signed out immediately/i,
    })
    await checkbox.click()
    await dialog.getByRole('button', { name: 'Revoke all tokens' }).click()

    await expect(app.getByRole('heading', { name: /Failed to revoke tokens/i })).toBeVisible({ timeout: 10_000 })
    await expect(dialog).not.toBeVisible()

    await expect(app.getByRole('button', { name: 'Revoke all tokens' })).toBeVisible()
  })
})

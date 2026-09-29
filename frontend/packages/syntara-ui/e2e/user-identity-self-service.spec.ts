/**
 * Self-Service Identity E2E Tests (UI-20, UI-21, UI-22, UI-23)
 *
 * Critical paths covered:
 * - Connect Flow (UI-20): federated user sees linked/unlinked providers, Connect link
 * - Disconnect Flow (UI-21): federated user disconnects one of multiple identities
 * - Last Identity Block (UI-22): cannot disconnect sole sign-in identity
 * - Duplicate Identity Error (UI-23): error when linking an already-linked identity
 *
 * Uses Playwright route interception to mock API responses. No backend data is
 * created or modified; route intercepts are cleared automatically after each test.
 */
import { test, expect, toAppUrl } from './fixtures'
import {
  ACCESS_URL,
  FEDERATED_USER_ID,
  IDENTITY_ID_3,
  federatedUserResponse,
  federatedUserIdentity,
  federatedUserIdentity2,
  oneProviderResponse,
  twoProvidersResponse,
  fulfill,
  mockUserIdentities,
  mockUser,
  mockAuthMe,
  mockAuthProviders,
} from './utils/mockData'

test.describe('Connect Flow (UI-20)', () => {
  test('federated user sees linked identity and Connect for unlinked provider', async ({ app }) => {
    await mockUserIdentities(app, FEDERATED_USER_ID, {
      resources: [federatedUserIdentity],
    })
    await mockUser(app, FEDERATED_USER_ID, federatedUserResponse)
    await mockAuthMe(app, federatedUserResponse)
    await mockAuthProviders(app, twoProvidersResponse)

    await app.goto(toAppUrl(`${ACCESS_URL}/${FEDERATED_USER_ID}/identities`))

    // Linked identity (Provider A) is listed
    const linkedRow = app.getByRole('row').filter({ hasText: 'Corporate SSO' })
    await expect(linkedRow).toBeVisible({ timeout: 15_000 })

    // last_used_at timestamp is displayed (not '-')
    const lastAuthCell = linkedRow.locator('td[data-label="Last authenticated"]')
    await expect(lastAuthCell).not.toHaveText('-')

    // Unlinked provider (Provider B) shows "Not connected"
    const unlinkedRow = app.getByRole('row').filter({ hasText: 'Keycloak' })
    await expect(unlinkedRow).toBeVisible()
    await expect(unlinkedRow.getByText('Not connected')).toBeVisible()

    // Connect action is available in the kebab menu for the unlinked provider
    const kebabButton = unlinkedRow.getByRole('button', { name: 'Identity actions' })
    await kebabButton.click()
    const connectItem = app.getByRole('menuitem', { name: 'Connect identity' })
    await expect(connectItem).toBeVisible()
    await expect(connectItem).not.toHaveAttribute('aria-disabled', 'true')
  })
})

test.describe('Disconnect Flow (UI-21)', () => {
  test('federated user disconnects one of multiple linked identities', async ({ app }) => {
    let identityDetached = false

    // DELETE the Keycloak identity — registered before the broader GET route
    await app.route(`**/api/v1/users/${FEDERATED_USER_ID}/identities/${IDENTITY_ID_3}`, (route) => {
      identityDetached = true
      return route.fulfill({ status: 204, body: '' })
    })

    // GET identities — both before DELETE, only Corporate SSO after
    await app.route(`**/api/v1/users/${FEDERATED_USER_ID}/identities`, (route) =>
      route.fulfill(
        fulfill({
          resources: identityDetached ? [federatedUserIdentity] : [federatedUserIdentity, federatedUserIdentity2],
        })
      )
    )

    await mockUser(app, FEDERATED_USER_ID, federatedUserResponse)
    await mockAuthMe(app, federatedUserResponse)
    await mockAuthProviders(app, twoProvidersResponse)

    await app.goto(toAppUrl(`${ACCESS_URL}/${FEDERATED_USER_ID}/identities`))

    // Both identities are visible
    await expect(app.getByRole('row').filter({ hasText: 'Corporate SSO' })).toBeVisible({ timeout: 15_000 })
    await expect(app.getByRole('row').filter({ hasText: 'Keycloak' })).toBeVisible()

    // Open the kebab menu on the Keycloak row and click Disconnect
    const keycloakRow = app.getByRole('row').filter({ hasText: 'Keycloak' })
    await keycloakRow.getByRole('button', { name: 'Identity actions' }).click()
    await app.getByRole('menuitem', { name: 'Disconnect identity' }).click()

    // Confirmation dialog with identity details
    const dialog = app.getByRole('dialog', { name: 'Disconnect identity?' })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText('Disconnecting will remove sign-in access')).toBeVisible()
    await expect(dialog.getByText('Keycloak', { exact: true })).toBeVisible()
    await expect(dialog.getByText('asmith')).toBeVisible()

    // Confirm disconnect
    await dialog.getByRole('button', { name: 'Disconnect identity' }).click()

    // Success alert and remaining identity unaffected
    await expect(app.getByText('Identity disconnected')).toBeVisible({ timeout: 10_000 })
    await expect(app.getByRole('row').filter({ hasText: 'Corporate SSO' })).toBeVisible()

    // Keycloak reverts to unlinked state
    await expect(app.getByRole('row').filter({ hasText: 'Keycloak' }).getByText('Not connected')).toBeVisible()
  })
})

test.describe('Last Identity Block (UI-22)', () => {
  test('federated user cannot disconnect their only linked identity', async ({ app }) => {
    await mockUserIdentities(app, FEDERATED_USER_ID, {
      resources: [federatedUserIdentity],
    })
    await mockUser(app, FEDERATED_USER_ID, federatedUserResponse)
    await mockAuthMe(app, federatedUserResponse)
    await mockAuthProviders(app, oneProviderResponse)

    await app.goto(toAppUrl(`${ACCESS_URL}/${FEDERATED_USER_ID}/identities`))

    // The linked identity is visible
    await expect(app.getByRole('row').filter({ hasText: 'Corporate SSO' })).toBeVisible({ timeout: 15_000 })

    // Open the kebab menu — Disconnect item is present but aria-disabled
    const kebabButton = app.getByRole('button', { name: 'Identity actions' })
    await kebabButton.click()
    const disconnectItem = app.getByRole('menuitem', { name: 'Disconnect identity' })
    await expect(disconnectItem).toBeVisible()
    await expect(disconnectItem).toHaveAttribute('aria-disabled', 'true')

    // Tooltip explains why disconnect is blocked
    await disconnectItem.hover()
    await expect(app.getByText('Cannot disconnect the only sign-in method')).toBeVisible()
  })
})

test.describe('Duplicate Identity Error (UI-23)', () => {
  test('displays error when linking an identity already linked to another user', async ({ app }) => {
    await mockUserIdentities(app, FEDERATED_USER_ID, {
      resources: [federatedUserIdentity],
    })
    await mockUser(app, FEDERATED_USER_ID, federatedUserResponse)
    await mockAuthMe(app, federatedUserResponse)
    await mockAuthProviders(app, twoProvidersResponse)

    // Simulate redirect back from IdP with link_error error code
    const url = `${ACCESS_URL}/${FEDERATED_USER_ID}/identities?link_error=identity_already_linked`
    await app.goto(toAppUrl(url))

    // Danger alert is displayed with the sanitized error message
    await expect(app.getByText('Failed to link identity')).toBeVisible({ timeout: 15_000 })
    await expect(app.getByText('This identity is already linked to another user.')).toBeVisible()

    // Identities remain unchanged — only the original identity is linked
    await expect(app.getByRole('row').filter({ hasText: 'Corporate SSO' })).toBeVisible()

    // Unlinked provider still shows "Not connected" (no new link was created)
    await expect(app.getByRole('row').filter({ hasText: 'Keycloak' }).getByText('Not connected')).toBeVisible()

    // link_error param is removed from the URL
    await expect(app).not.toHaveURL(/link_error/)
  })
})

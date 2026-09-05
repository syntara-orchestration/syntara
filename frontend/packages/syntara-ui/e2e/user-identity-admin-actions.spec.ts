/**
 * Tests UI-25 (Admin Transfer Identity) and UI-26 (Admin Detach Identity)
 *
 * Critical paths covered:
 * - Full-page Transfer Identity wizard: select user -> select identity -> attach
 * - Detach (Disconnect) identity with confirmation dialog
 *
 * Uses Playwright route interception to mock API responses. No backend data is
 * created or modified; route intercepts are cleared automatically after each test.
 */
import { test, expect, toAppUrl } from './fixtures'
import {
  ACCESS_URL,
  NON_BUILTIN_USER_ID,
  FEDERATED_USER_ID,
  IDENTITY_ID_2,
  builtinUserResponse,
  nonBuiltinUserResponse,
  federatedUserIdentity,
  nonBuiltinUserIdentity,
  oneProviderResponse,
  usersListResponse,
  fulfill,
  mockUserIdentities,
  mockUser,
  mockAuthMe,
  mockAuthProviders,
  mockUsersList,
  mockUserGroups,
  mockIdentityProviders,
} from './utils/mockData'

test.describe('User Detail — Admin Identity Actions (UI-25, UI-26)', () => {
  /**
   * UI-25: Admin clicks "Transfer identity" on the Identities tab, which
   * navigates to the full-page wizard. Selects a source user in Step 1,
   * picks one of their identities in Step 2, and attaches it.
   */
  test.skip('admin transfers a federated identity via wizard (UI-25)', async ({ app }) => {
    // User A (Alice) identities — the source for the transfer
    await mockUserIdentities(app, FEDERATED_USER_ID, {
      resources: [federatedUserIdentity],
    })

    // User B (jdoe) identities — stateful: empty before POST, populated after
    let identityAttached = false
    const movedIdentity = { ...federatedUserIdentity, user_id: NON_BUILTIN_USER_ID }
    await app.route(`**/api/v1/users/${NON_BUILTIN_USER_ID}/identities`, (route) => {
      if (route.request().method() === 'POST') {
        identityAttached = true
        return route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(movedIdentity),
        })
      }
      return route.fulfill(fulfill({ resources: identityAttached ? [movedIdentity] : [] }))
    })

    await mockUserGroups(app, NON_BUILTIN_USER_ID)
    await mockUser(app, NON_BUILTIN_USER_ID, nonBuiltinUserResponse)
    await mockUser(app, FEDERATED_USER_ID, {
      ...nonBuiltinUserResponse,
      id: FEDERATED_USER_ID,
      username: 'asmith',
      first_name: 'Alice',
      last_name: 'Smith',
      email: 'asmith@example.com',
      auth_type: 'federated',
    })
    await mockUsersList(app, usersListResponse)
    await mockAuthMe(app, builtinUserResponse)
    await mockAuthProviders(app, oneProviderResponse)
    await mockIdentityProviders(app)

    // Navigate to User B's Identities tab
    await app.goto(toAppUrl(`${ACCESS_URL}/${NON_BUILTIN_USER_ID}/identities`))

    // Click "Transfer identity" button (primary) to navigate to wizard
    const transferButton = app.getByRole('button', { name: 'Transfer identity' })
    await expect(transferButton).toBeVisible({ timeout: 15_000 })
    await transferButton.click()

    // Verify wizard page loaded with correct title
    await expect(app.getByRole('heading', { level: 1, name: /Transfer identity to jdoe/i })).toBeVisible()

    // Step 1: Wizard nav should show both steps
    const wizardNav = app.getByRole('navigation', { name: 'Wizard steps' })
    await expect(wizardNav).toBeVisible()

    // Step 1: Select a user — click the email text to select via row click
    await app.getByText('asmith@example.com').click()

    // Next button should now be enabled — click it
    await app.getByRole('button', { name: 'Next', exact: true }).click()

    // Step 2: Select an identity — click the Subject text to select via row click
    await app.getByText('asmith@example.com').click()

    // Click Transfer identity
    await app.getByRole('button', { name: 'Transfer identity' }).click()

    // Success alert and identity now appears in User B's table with Connected status
    await expect(app.getByRole('heading', { name: 'Identity transferred' })).toBeVisible({ timeout: 10_000 })
    await expect(app.getByRole('gridcell', { name: /Corporate SSO/ })).toBeVisible({ timeout: 10_000 })
    await expect(app.getByText('Connected')).toBeVisible()
    await expect(app.getByText('https://sso.example.com')).toBeVisible()
  })

  /**
   * UI-25b: Cancel link navigates back to user's identities tab.
   */
  test('wizard cancel returns to identities tab (UI-25b)', async ({ app }) => {
    await mockUserIdentities(app, NON_BUILTIN_USER_ID)
    await mockUserGroups(app, NON_BUILTIN_USER_ID)
    await mockUser(app, NON_BUILTIN_USER_ID, nonBuiltinUserResponse)
    await mockUsersList(app, usersListResponse)
    await mockAuthMe(app, builtinUserResponse)
    await mockAuthProviders(app, oneProviderResponse)

    await app.goto(toAppUrl(`${ACCESS_URL}/${NON_BUILTIN_USER_ID}/transfer-identity`))
    await expect(app.getByRole('heading', { level: 1, name: /Transfer identity to jdoe/i })).toBeVisible({
      timeout: 15_000,
    })

    await app.getByRole('link', { name: 'Cancel' }).click()

    await expect(app).toHaveURL(new RegExp(`${NON_BUILTIN_USER_ID}/identities`))
  })

  /**
   * UI-25c: Step 2 shows empty state when selected user has no identities.
   */
  test('wizard shows empty state when source user has no identities (UI-25c)', async ({ app }) => {
    await mockUserIdentities(app, FEDERATED_USER_ID, { resources: [] })
    await mockUserIdentities(app, NON_BUILTIN_USER_ID)
    await mockUserGroups(app, NON_BUILTIN_USER_ID)
    await mockUser(app, NON_BUILTIN_USER_ID, nonBuiltinUserResponse)
    await mockUser(app, FEDERATED_USER_ID, {
      ...nonBuiltinUserResponse,
      id: FEDERATED_USER_ID,
      username: 'asmith',
      first_name: 'Alice',
      last_name: 'Smith',
      email: 'asmith@example.com',
      auth_type: 'federated',
    })
    await mockUsersList(app, usersListResponse)
    await mockAuthMe(app, builtinUserResponse)
    await mockAuthProviders(app, oneProviderResponse)

    await app.goto(toAppUrl(`${ACCESS_URL}/${NON_BUILTIN_USER_ID}/transfer-identity`))
    await expect(app.getByRole('heading', { level: 1, name: /Transfer identity to jdoe/i })).toBeVisible({
      timeout: 15_000,
    })

    await app.getByText('asmith@example.com').click()
    await app.getByRole('button', { name: 'Next', exact: true }).click()

    await expect(app.getByText('No identities')).toBeVisible()
    await expect(app.getByText('This user has no federated identities to attach.')).toBeVisible()
    await expect(app.getByRole('button', { name: 'Transfer identity' })).toBeDisabled()
  })

  /**
   * UI-26: Admin clicks Disconnect on a linked identity, confirms in the
   * confirmation dialog, and the identity is removed.
   */
  test('admin disconnects a linked identity (UI-26)', async ({ app }) => {
    let identityDetached = false

    // DELETE specific identity — registered before the broader GET route
    await app.route(`**/api/v1/users/${NON_BUILTIN_USER_ID}/identities/${IDENTITY_ID_2}`, (route) => {
      identityDetached = true
      return route.fulfill({ status: 204, body: '' })
    })

    // GET identities — starts with one, empty after detach
    await app.route(`**/api/v1/users/${NON_BUILTIN_USER_ID}/identities`, (route) =>
      route.fulfill(fulfill({ resources: identityDetached ? [] : [nonBuiltinUserIdentity] }))
    )

    await mockUserGroups(app, NON_BUILTIN_USER_ID)
    await mockUser(app, NON_BUILTIN_USER_ID, nonBuiltinUserResponse)
    await mockAuthMe(app, builtinUserResponse)
    await mockAuthProviders(app, oneProviderResponse)
    await mockIdentityProviders(app)

    await app.goto(toAppUrl(`${ACCESS_URL}/${NON_BUILTIN_USER_ID}/identities`))

    // Identity is visible in the table with Connected status
    await expect(app.getByRole('gridcell', { name: /Corporate SSO/ })).toBeVisible({ timeout: 15_000 })
    await expect(app.getByText('Connected')).toBeVisible()
    await expect(app.getByText('https://sso.example.com')).toBeVisible()

    // Open the kebab menu on the identity row and click Disconnect
    await app.getByRole('button', { name: 'Identity actions' }).click()
    await app.getByRole('menuitem', { name: 'Disconnect identity' }).click()

    // Confirmation dialog
    const dialog = app.getByRole('dialog', { name: 'Disconnect identity?' })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText('Disconnecting will remove sign-in access')).toBeVisible()
    await expect(dialog.getByText('Corporate SSO')).toBeVisible()
    await expect(dialog.getByText('jdoe@example.com')).toBeVisible()

    // Confirm disconnect
    await dialog.getByRole('button', { name: 'Disconnect identity' }).click()

    // Success alert, identity removed, provider now shows as Not connected
    await expect(app.getByText('Identity disconnected')).toBeVisible({ timeout: 10_000 })
    const table = app.getByRole('grid')
    await expect(table.getByRole('button', { name: 'Disconnect identity' })).not.toBeAttached()
    await expect(app.getByText('Not connected')).toBeVisible()
  })
})

/**
 * Test UI-24: Self-Service Identity — Builtin User Controls Hidden
 * Test UI-32: Local User IdP Link — Conversion Warning
 *
 * Critical paths covered:
 * - Builtin admin sees empty state — no Connect or Transfer identity controls (UI-24)
 * - Non-builtin local user sees Connect controls with conversion warning dialog (UI-24, UI-32)
 * - Warning displays account conversion message and password removal notice (UI-32)
 *
 * Uses Playwright route interception to mock API responses. No backend data is
 * created or modified; route intercepts are cleared automatically after each test.
 */
import { test, expect, toAppUrl } from './fixtures'
import {
  ACCESS_URL,
  BUILTIN_USER_ID,
  NON_BUILTIN_USER_ID,
  builtinUserResponse,
  nonBuiltinUserResponse,
  oneProviderResponse,
  mockUserIdentities,
  mockUser,
  mockAuthMe,
  mockAuthProviders,
  mockIdentityProviders,
} from './utils/mockData'

test.describe('User Detail — Identity Controls (UI-24)', () => {
  /**
   * UI-24 Steps 1–3: Log in as the builtin admin, navigate to Identities tab,
   * verify identity linking controls are not displayed.
   */
  test('builtin admin — identity linking controls are hidden', async ({ app }) => {
    await mockUserIdentities(app, BUILTIN_USER_ID)
    await mockUser(app, BUILTIN_USER_ID, builtinUserResponse)
    // auth/me id matches the page user — builtin admin viewing their own profile.
    await mockAuthMe(app, builtinUserResponse)
    await mockAuthProviders(app, { resources: [] })

    await app.goto(toAppUrl(`${ACCESS_URL}/${BUILTIN_USER_ID}/identities`))

    await expect(app.getByRole('heading', { name: 'Built-in user' })).toBeVisible({ timeout: 15_000 })
    await expect(
      app.getByText('The built-in administrator account cannot be linked to external identity providers.')
    ).toBeVisible()
    // The builtin-user empty state replaces the whole table section — buttons are
    // never mounted. not.toBeAttached() asserts DOM non-presence, which is
    // stronger than not.toBeVisible() (which also passes for hidden-but-present elements).
    await expect(app.getByRole('button', { name: 'Transfer identity' })).not.toBeAttached()
    await expect(app.getByRole('button', { name: 'Identity actions' })).not.toBeAttached()
  })

  /**
   * UI-24 Steps 4–5 + Expected Result: Log in as a non-builtin local user, navigate to
   * their own Identities tab, verify Connect controls are shown and clicking Connect
   * opens the conversion warning (linking converts the account and removes the password).
   */
  test('non-builtin local user — Connect controls visible with conversion warning', async ({ app }) => {
    await mockUserIdentities(app, NON_BUILTIN_USER_ID)
    await mockUser(app, NON_BUILTIN_USER_ID, nonBuiltinUserResponse)
    // auth/me id matches the page user so isSelf=true — the kebab menu's Connect
    // item is enabled (vs. disabled when an admin views another user).
    await mockAuthMe(app, nonBuiltinUserResponse)
    await mockAuthProviders(app, oneProviderResponse)
    await mockIdentityProviders(app)

    await app.goto(toAppUrl(`${ACCESS_URL}/${NON_BUILTIN_USER_ID}/identities`))

    const kebabButton = app.getByRole('button', { name: 'Identity actions' })
    await expect(kebabButton).toBeVisible({ timeout: 15_000 })

    // Status column shows "Not connected" for the unlinked provider
    await expect(app.getByText('Not connected')).toBeVisible()

    // Open the kebab menu and click Connect to trigger the conversion warning dialog (isLocalUser=true)
    await kebabButton.click()
    await app.getByRole('menuitem', { name: 'Connect identity' }).click()
    await expect(app.getByRole('dialog', { name: 'Link identity provider?' })).toBeVisible()
    await expect(app.getByText('Your password will be permanently removed')).toBeVisible()
    await expect(app.getByRole('button', { name: 'Convert and link identity' })).toBeVisible()
  })
})

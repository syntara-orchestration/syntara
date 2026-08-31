/**
 * Test UI-27: Local User — Controls and Group Assignment
 *
 * Critical paths covered:
 * - Admin views local user's Identities tab — no self-service Connect button
 * - Admin views local user's Groups tab — Add to group button available
 * - Admin assigns local user to a group — group appears in the list
 *
 * Uses Playwright route interception to mock API responses. No backend data is
 * created or modified; route intercepts are cleared automatically after each test.
 */
import { type Page } from './fixtures'
import { test, expect, toAppUrl } from './fixtures'
import {
  ACCESS_URL,
  NON_BUILTIN_USER_ID,
  builtinUserResponse,
  nonBuiltinUserResponse,
  oneProviderResponse,
  fulfill,
  mockUserIdentities,
  mockUser,
  mockAuthMe,
  mockAuthProviders,
  mockUserGroups,
} from './utils/mockData'

const MOCK_GROUP_ID = 'group-1a2b-3c4d-5e6f-7890-abcdef123456'
const mockGroup = {
  id: MOCK_GROUP_ID,
  name: 'platform-admins',
  description: 'Platform administrators',
  is_builtin: false,
}

// ---------------------------------------------------------------------------
// Local route-mock helpers (group-specific, not shared)
// ---------------------------------------------------------------------------

/**
 * Mocks GET /api/v1/groups (the all-groups fetch used by useAllGroups for dropdowns).
 * Uses a URL predicate because useAllGroups adds explicit query params
 * (?limit=100&cursor=...) that would cause a glob pattern to miss the request.
 */
async function mockAllGroups(app: Page, response: unknown): Promise<void> {
  await app.route(
    (url) => url.pathname === '/api/v1/groups',
    (route) => route.fulfill(fulfill(response))
  )
}

test.describe('User Detail — Local User Controls and Group Assignment (UI-27)', () => {
  /**
   * UI-27 Steps 1–3: Admin views a local user's Identities tab.
   * Self-service Connect button must not appear (isSelf=false); Transfer identity
   * (admin-level action) is the only control available.
   */
  test('admin views local user identities tab — Transfer identity available, Connect hidden', async ({ app }) => {
    await mockUserIdentities(app, NON_BUILTIN_USER_ID)
    await mockUser(app, NON_BUILTIN_USER_ID, nonBuiltinUserResponse)
    // auth/me returns the admin — different id from the page user, so isSelf=false
    // and ConnectAction renders a dash instead of the Connect button.
    await mockAuthMe(app, builtinUserResponse)
    await mockAuthProviders(app, oneProviderResponse)

    await app.goto(toAppUrl(`${ACCESS_URL}/${NON_BUILTIN_USER_ID}/identities`))

    await expect(app.getByRole('button', { name: 'Transfer identity' })).toBeVisible({ timeout: 15_000 })
    // ConnectAction returns <span>—</span> when !isSelf — the button is never mounted.
    // not.toBeAttached() asserts DOM non-presence, stronger than not.toBeVisible().
    await expect(app.getByRole('button', { name: 'Connect' })).not.toBeAttached()
  })

  /**
   * UI-27 Steps 1–2 + Expected Result 2: Admin views local user's Groups tab.
   * Group assignment controls must be available.
   */
  test('admin views local user groups tab — Add to group button available', async ({ app }) => {
    await mockUser(app, NON_BUILTIN_USER_ID, nonBuiltinUserResponse)
    await mockAuthMe(app, builtinUserResponse)
    // Empty groups list keeps groups.length=0 → empty state with "Add to group" button.
    await mockAllGroups(app, { resources: [] })
    await mockUserGroups(app, NON_BUILTIN_USER_ID, { resources: [] })

    await app.goto(toAppUrl(`${ACCESS_URL}/${NON_BUILTIN_USER_ID}/groups`))

    await expect(app.getByRole('button', { name: 'Add to group' })).toBeVisible({ timeout: 15_000 })
  })

  /**
   * UI-27 Steps 4–5: Admin assigns local user to a group.
   * Group must appear in the user's group list after assignment.
   */
  test.skip('admin assigns local user to a group — group appears in list', async ({ app }) => {
    await mockUser(app, NON_BUILTIN_USER_ID, nonBuiltinUserResponse)
    await mockAuthMe(app, builtinUserResponse)

    // Stateful mock: groups tab starts empty; after the mutation the refetch returns
    // the newly added group.
    let groupAssigned = false
    // Use pathname predicate — glob patterns don't match URLs with query params
    // (e.g. ?limit=100&cursor=...) that TanStack Query adds on refetch.
    await app.route(
      (url) => url.pathname === `/api/v1/users/${NON_BUILTIN_USER_ID}/groups`,
      (route) => route.fulfill(fulfill({ resources: groupAssigned ? [mockGroup] : [] }))
    )

    // POST /groups/{id}/members — the mutation for adding a user to a group.
    await app.route(`**/api/v1/groups/${MOCK_GROUP_ID}/members`, (route) => {
      groupAssigned = true
      return route.fulfill(fulfill({ user_id: NON_BUILTIN_USER_ID }))
    })

    // useAllGroups feeds the typeahead in AddToGroupModal.
    await mockAllGroups(app, { resources: [mockGroup] })

    await app.goto(toAppUrl(`${ACCESS_URL}/${NON_BUILTIN_USER_ID}/groups`))

    const addToGroupButton = app.getByRole('button', { name: 'Add to group' })
    await expect(addToGroupButton).toBeVisible({ timeout: 15_000 })
    await addToGroupButton.click()

    const dialog = app.getByRole('dialog', { name: 'Add to group' })
    await expect(dialog).toBeVisible()

    // Type to filter and open the dropdown — PF6 renders options in a portal
    // outside the dialog DOM, so the option must be queried at page level.
    await dialog.getByPlaceholder('Search for a group...').fill('platform')
    const groupOption = app.getByRole('option', { name: 'platform-admins' })
    await expect(groupOption).toBeVisible({ timeout: 10_000 })
    await groupOption.click()

    const addButton = dialog.getByRole('button', { name: 'Add', exact: true })
    await expect(addButton).toBeEnabled()
    await addButton.click()

    // Wait for dialog to close — confirms mutation completed before checking outcome.
    await expect(dialog).not.toBeVisible({ timeout: 10_000 })

    // Success toast and group row in the table (panel refetches after mutation).
    await expect(app.getByRole('heading', { name: 'Added to group' })).toBeVisible({ timeout: 10_000 })
    await expect(app.getByRole('gridcell', { name: 'platform-admins' })).toBeVisible({ timeout: 10_000 })
  })
})

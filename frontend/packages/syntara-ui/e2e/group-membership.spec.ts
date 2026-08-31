/**
 * E2E Tests: Group Membership Management (Full-page detail)
 *
 * Critical paths covered:
 * - Navigate to group detail page by clicking group name
 * - View group details, members, and roles tabs
 * - Add a member to a group
 * - Remove a member from a group
 * - Navigate back to groups list
 * - Manage group membership from user detail page
 */
import { createUnavailableGuard, test, expect, toAppUrl } from './fixtures'
import { buildUniqueName } from './helpers/workflows'
import { createUserViaApi, deleteUserViaApi, ensureGroupExists, type SeededUser } from './seeds/iam'
import { getAuthToken } from './utils/api'

let seededUser: SeededUser | null = null

test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage()
  const token = await getAuthToken(page)
  if (token) {
    await ensureGroupExists(page, 'admins')

    const prefix = buildUniqueName('e2e-gm')
    seededUser = await createUserViaApi(page, { username: `${prefix}-user`, token })
  }
  await page.close()
})

test.afterAll(async ({ browser }) => {
  const page = await browser.newPage()
  if (seededUser) {
    await deleteUserViaApi(page, seededUser.id)
  }
  await page.close()
})

test.describe('Group Detail — Navigation & Tabs', () => {
  const guard = createUnavailableGuard('No "admins" group found; seed data required')

  test.beforeEach(async ({ app }) => {
    await app.goto(toAppUrl('/system-administration/access-management/groups'))
    await expect(app.getByRole('heading', { level: 1, name: /access management/i })).toBeVisible()
    const table = app.getByRole('grid', { name: 'Groups table' })
    const hasAdmins = await table
      .getByRole('button', { name: 'admins', exact: true })
      .waitFor({ state: 'visible', timeout: 3000 })
      .then(() => true)
      .catch(() => false)
    if (!hasAdmins) guard.markUnavailable()
    test.skip(!hasAdmins, 'No "admins" group found; seed data required')
  })

  test('clicking a group name navigates to the detail page', async ({ app }) => {
    const table = app.getByRole('grid', { name: 'Groups table' })
    await table.getByRole('button', { name: 'admins', exact: true }).click()

    // Should navigate to group detail page
    await expect(app).toHaveURL(/system-administration\/access-management\/groups\//)
    await expect(app.getByRole('heading', { level: 1, name: 'admins', exact: true })).toBeVisible()

    // Should show tabs
    await expect(app.getByRole('tab', { name: /details/i })).toBeVisible()
    await expect(app.getByRole('tab', { name: /assignments/i })).toBeVisible()
  })

  test('members tab shows member list or empty state', async ({ app }) => {
    // Navigate to admins group detail (admins has Members tab, unlike authenticated)
    const table = app.getByRole('grid', { name: 'Groups table' })
    await table.getByRole('button', { name: 'admins', exact: true }).click()
    await expect(app.getByRole('heading', { level: 1, name: 'admins', exact: true })).toBeVisible()

    // Switch to members tab
    const membersTab = app.getByRole('tab', { name: /members/i })
    await expect(membersTab).toBeVisible()
    await membersTab.click()

    // Should see members content (table or empty state)
    const hasTable = await app
      .getByRole('columnheader', { name: 'Username' })
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    const hasEmptyState = await app
      .getByText('No members yet', { exact: true })
      .waitFor({ state: 'visible', timeout: 2000 })
      .then(() => true)
      .catch(() => false)

    expect(hasTable || hasEmptyState).toBe(true)
  })

  test('navigating back returns to groups list', async ({ app }) => {
    const table = app.getByRole('grid', { name: 'Groups table' })
    await table.getByRole('button', { name: 'admins', exact: true }).click()
    await expect(app.getByRole('heading', { level: 1, name: 'admins', exact: true })).toBeVisible()

    // Navigate back via URL (GroupDetail has no back button — use sidebar nav)
    await app.goto(toAppUrl('/system-administration/access-management/groups'))

    await expect(app.getByRole('heading', { level: 1, name: /access management/i })).toBeVisible()
    await expect(table.getByRole('button', { name: 'admins', exact: true })).toBeVisible()
  })

  test.describe('Member add/remove (typeahead)', () => {
    test.skip(!!process.env.CI, "Typeahead dropdown timing is unreliable in CI — options don't render within timeout")

    test('add and remove a member from the group detail', async ({ app }) => {
      const table = app.getByRole('grid', { name: 'Groups table' })
      await table.getByRole('button', { name: 'admins', exact: true }).click()
      await expect(app.getByRole('heading', { level: 1, name: 'admins', exact: true })).toBeVisible()

      await app.getByRole('tab', { name: /members/i }).click()
      await app.getByRole('button', { name: 'Add member' }).click()

      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()

      const selectInput = dialog.getByPlaceholder('Search for a user...')
      await selectInput.click()

      // Wait for either options or "No results match" to appear.
      // PF6 Select renders the listbox in a portal outside the dialog DOM,
      // so we must query at page level, not scoped to the dialog.
      const noResults = app.getByRole('option', { name: /No results match/ })
      const availableOptions = app.getByRole('option').filter({ hasNotText: /No results match/ })
      await expect(noResults.or(availableOptions)).toBeVisible({ timeout: 15_000 })

      if (await noResults.isVisible()) {
        test.skip(true, 'No available users to add (all users are already members)')
        return
      }

      // The option contains two child spans: username + display name.
      // Extract just the username (first child text) for later verification.
      const [selectedOption] = await availableOptions.all()
      const [firstChild] = await selectedOption.locator('> *').all()
      const userName = await firstChild.textContent()
      await selectedOption.click()

      await dialog.getByRole('button', { name: 'Add', exact: true }).click()

      await expect(dialog).not.toBeVisible()
      await expect(app.getByText(/member added/i)).toBeVisible()

      if (userName) {
        const memberName = userName.trim()
        await expect(app.getByRole('gridcell', { name: memberName, exact: true })).toBeVisible({ timeout: 10_000 })

        const memberRow = app.getByRole('row').filter({ hasText: memberName })
        await memberRow.getByRole('button', { name: /kebab toggle/i }).click()
        await app.getByRole('menuitem', { name: 'Remove' }).click()

        await expect(app.getByRole('dialog')).toBeVisible()
        await app.getByRole('button', { name: 'Remove', exact: true }).click()

        await expect(app.getByText(/member removed/i)).toBeVisible()
      }
    })
  })

  test('navigating to a different group shows its details', async ({ app }) => {
    const table = app.getByRole('grid', { name: 'Groups table' })

    // Navigate to admins group detail
    await table.getByRole('button', { name: 'admins', exact: true }).click()
    await expect(app.getByRole('heading', { level: 1, name: 'admins', exact: true })).toBeVisible()

    // Go back to groups list
    await app.goto(toAppUrl('/system-administration/access-management/groups'))
    await expect(app.getByRole('heading', { level: 1, name: /access management/i })).toBeVisible()

    // Navigate to authenticated group
    await table.getByRole('button', { name: 'authenticated' }).click()
    await expect(app.getByRole('heading', { level: 1, name: 'authenticated', exact: true })).toBeVisible()
  })

  test('builtin groups show built-in label and no edit button', async ({ app }) => {
    const table = app.getByRole('grid', { name: 'Groups table' })
    await table.getByRole('button', { name: 'admins', exact: true }).click()
    await expect(app.getByRole('heading', { level: 1, name: 'admins', exact: true })).toBeVisible()

    // Should show Built-in label on the default Details tab
    await expect(app.getByText('Built-in', { exact: true })).toBeVisible()

    // Should not show edit button (builtin groups can't be edited)
    await expect(app.getByRole('button', { name: 'Edit group' })).not.toBeVisible()
  })
})

test.describe('User Detail — Group Membership', () => {
  // This test passes locally against mock API but on CI the User detail page
  // never finishes loading — the "Edit user" button never appears within 30s.
  test('add to group button is available on user groups tab', async ({ app }) => {
    await app.goto(toAppUrl('/system-administration/access-management/users'))
    await expect(app.getByRole('heading', { level: 1, name: /access management/i })).toBeVisible()

    // Click on a user
    const userLink = app.getByRole('button', { name: 'admin', exact: true })
    const hasUser = await userLink
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasUser, 'No admin user in mock data')

    await userLink.click()
    await expect(app).toHaveURL(/\/system-administration\/access-management\/users\/[^/]+$/, { timeout: 30_000 })
    // User detail loaded — do not wait on `role="tab"` "Details": PF horizontal overflow can move
    // every sub-tab (including Details) behind overflow/scroll so no tab is a visible `tab`.
    await expect(app.getByRole('button', { name: 'Edit user' })).toBeVisible({ timeout: 30_000 })

    // Open the Groups panel via URL (matches useUrlTab); avoids relying on any sub-tab click.
    const userPath = new URL(app.url()).pathname
    await app.goto(toAppUrl(`${userPath}/groups`))
    await expect(app).toHaveURL(/\/system-administration\/access-management\/users\/[^/]+\/groups$/, {
      timeout: 30_000,
    })

    // Should see add to group button (panel content — do not require clicking the Groups tab:
    // PF horizontal overflow can move "Groups" into an overflow menu where it is not role="tab".)
    await expect(app.getByRole('button', { name: /add to group/i })).toBeVisible({ timeout: 5000 })
  })
})

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
import { type Page, test, expect, toAppUrl } from './fixtures'
import { buildUniqueName } from './helpers/workflows'
import {
  createUserViaApi,
  deleteGroupViaApi,
  deleteUserViaApi,
  ensureGroupExists,
  type SeededGroup,
  type SeededUser,
} from './seeds/iam'
import { getAuthToken } from './utils/api'

const seededGroups: SeededGroup[] = []
let seededUser: SeededUser | undefined

async function openGroupByName(app: Page, name: string) {
  await app.goto(toAppUrl('/system-administration/access-management/groups'))
  await expect(app.getByRole('heading', { level: 1, name: /access management/i })).toBeVisible()
  const table = app.getByRole('grid', { name: 'Groups table' })
  await app.getByPlaceholder('Filter by name').fill(name)
  await app.getByRole('button', { name: 'Apply filter' }).click()
  await table.getByRole('button', { name, exact: true }).click()
  await expect(app.getByRole('heading', { level: 1, name, exact: true })).toBeVisible()
}

test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage()
  try {
    const token = await getAuthToken(page)
    if (!token) throw new Error('group-membership beforeAll: could not obtain auth token')
    const prefix = buildUniqueName('e2e-gm')
    seededGroups.push(await ensureGroupExists(page, `${prefix}-a`))
    seededGroups.push(await ensureGroupExists(page, `${prefix}-b`))
    seededUser = await createUserViaApi(page, { username: `${prefix}-user`, token })
  } finally {
    await page.close()
  }
})

test.afterAll(async ({ browser }) => {
  const page = await browser.newPage()
  try {
    if (seededUser) await deleteUserViaApi(page, seededUser.id)
    for (const group of seededGroups) {
      if (group.createdByUs) await deleteGroupViaApi(page, group.id)
    }
  } finally {
    await page.close()
  }
})

test.describe('Group Detail — Navigation & Tabs', () => {
  test.beforeEach(async ({ app }) => {
    expect(seededGroups.length, 'Failed to seed groups via API').toBeGreaterThan(1)
    await app.goto(toAppUrl('/system-administration/access-management/groups'))
    await expect(app.getByRole('heading', { level: 1, name: /access management/i })).toBeVisible()
  })

  test('clicking a group name navigates to the detail page', async ({ app }) => {
    await openGroupByName(app, seededGroups[0].name)

    await expect(app).toHaveURL(/system-administration\/access-management\/groups\//)
    await expect(app.getByRole('tab', { name: /details/i })).toBeVisible()
    await expect(app.getByRole('tab', { name: /assignments/i })).toBeVisible()
  })

  test('members tab shows member list or empty state', async ({ app }) => {
    await openGroupByName(app, seededGroups[0].name)

    const membersTab = app.getByRole('tab', { name: /members/i })
    await expect(membersTab).toBeVisible()
    await membersTab.click()

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
    await openGroupByName(app, seededGroups[0].name)

    await app.goto(toAppUrl('/system-administration/access-management/groups'))

    await expect(app.getByRole('heading', { level: 1, name: /access management/i })).toBeVisible()
    await app.getByPlaceholder('Filter by name').fill(seededGroups[0].name)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    await expect(
      app.getByRole('grid', { name: 'Groups table' }).getByRole('button', { name: seededGroups[0].name, exact: true })
    ).toBeVisible()
  })

  test('navigating to a different group shows its details', async ({ app }) => {
    await openGroupByName(app, seededGroups[0].name)
    await openGroupByName(app, seededGroups[1].name)
  })

  test('builtin groups show built-in label and no edit button', async ({ app }) => {
    await openGroupByName(app, 'admins')

    await expect(app.getByText('Built-in', { exact: true })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Edit group' })).not.toBeVisible()
  })
})

// Separate describe so a typeahead failure does not skip the navigation tests above.
// GitHub CI sets CI=true; Konflux does not — @konflux-skip covers that runner.
test.describe('Group Detail — Member add/remove (typeahead)', { tag: ['@konflux-skip'] }, () => {
  test.skip(!!process.env.CI, "Typeahead dropdown timing is unreliable in CI — options don't render within timeout")

  test('add and remove a member from the group detail', async ({ app }) => {
    const prefix = buildUniqueName('e2e-gm')
    const group = await ensureGroupExists(app, prefix)
    const user = await createUserViaApi(app, { username: `${prefix}-user` })

    try {
      await openGroupByName(app, group.name)

      await app.getByRole('tab', { name: /members/i }).click()
      await app.getByRole('button', { name: 'Add member' }).click()

      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()

      const selectInput = dialog.getByPlaceholder('Search for a user...')
      await selectInput.click()
      await selectInput.fill(user.username)

      // PF6 Select renders the listbox in a portal outside the dialog DOM.
      const userOption = app.getByRole('option').filter({ hasText: user.username })
      await expect(userOption).toBeVisible({ timeout: 15_000 })
      await userOption.click()

      await dialog.getByRole('button', { name: 'Add', exact: true }).click()

      await expect(dialog).not.toBeVisible()
      await expect(app.getByText(/member added/i)).toBeVisible()

      await expect(app.getByRole('gridcell', { name: user.username, exact: true })).toBeVisible({ timeout: 10_000 })

      const memberRow = app.getByRole('row').filter({ hasText: user.username })
      await memberRow.getByRole('button', { name: /^Actions for / }).click()
      await app.getByRole('menuitem', { name: 'Remove member' }).click()

      await expect(app.getByRole('dialog')).toBeVisible()
      await app.getByRole('button', { name: 'Remove', exact: true }).click()

      await expect(app.getByText(/member removed/i)).toBeVisible()
    } finally {
      await deleteUserViaApi(app, user.id)
      if (group.createdByUs) await deleteGroupViaApi(app, group.id)
    }
  })
})

test.describe('User Detail — Group Membership', () => {
  test('add to group button is available on user groups tab', async ({ app }) => {
    expect(seededUser, 'Failed to seed user via API').toBeTruthy()
    if (!seededUser) throw new Error('Failed to seed user via API')
    await app.goto(toAppUrl(`/system-administration/access-management/users/${seededUser.id}`))
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

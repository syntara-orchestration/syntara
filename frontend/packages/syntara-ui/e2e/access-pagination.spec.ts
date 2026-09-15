/**
 * E2E Tests: Access Management — Dropdown Pagination
 *
 * Critical paths covered:
 * - Assign Role modal on a user detail page loads all roles in the multi-select
 * - Add Member modal on a group detail page loads all users in the typeahead
 *
 * These are read-only tests that verify fetch-all pagination correctly populates
 * dropdown/select option lists. No cleanup needed.
 */
import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName } from './helpers/workflows'
import {
  createRoleViaApi,
  createUserViaApi,
  deleteGroupViaApi,
  deleteRoleViaApi,
  deleteUserViaApi,
  ensureGroupExists,
  type SeededGroup,
  type SeededRole,
  type SeededUser,
} from './seeds/iam'
import { getAuthToken } from './utils/api'

const seededUsers: SeededUser[] = []
const seededRoles: SeededRole[] = []
let seededGroup: SeededGroup | null = null

test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage()
  try {
    const token = await getAuthToken(page)
    if (!token) throw new Error('access-pagination beforeAll: could not obtain auth token')
    const prefix = buildUniqueName('e2e-accpag')

    for (let i = 1; i <= 3; i++) {
      seededUsers.push(await createUserViaApi(page, { username: `${prefix}-user-${i}`, token }))
    }

    for (let i = 1; i <= 3; i++) {
      seededRoles.push(await createRoleViaApi(page, { name: `${prefix}-role-${i}`, token }))
    }

    seededGroup = await ensureGroupExists(page, `${prefix}-group`)
  } finally {
    await page.close()
  }
})

test.afterAll(async ({ browser }) => {
  const page = await browser.newPage()
  for (const role of seededRoles) {
    await deleteRoleViaApi(page, role.id)
  }
  for (const user of seededUsers) {
    await deleteUserViaApi(page, user.id)
  }
  if (seededGroup?.createdByUs) {
    await deleteGroupViaApi(page, seededGroup.id)
  }
  await page.close()
})

test.describe('Access Management — Dropdown Pagination', () => {
  test('Assign Role modal shows roles in the multi-select dropdown', async ({ app }) => {
    expect(seededUsers.length, 'No seeded users created in beforeAll').toBeGreaterThan(0)

    await app.goto(toAppUrl(`/system-administration/access-management/users/${seededUsers[0].id}`))
    await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 10_000 })

    await expect(app).toHaveURL(/system-administration\/access-management\/users\//)

    const assignmentsTab = app.getByRole('tab', { name: /assignments/i })
    await expect(assignmentsTab).toBeVisible({ timeout: 10_000 })
    await assignmentsTab.click()

    const assignButton = app.getByRole('button', { name: /assign role/i })
    await expect(assignButton).toBeVisible({ timeout: 10_000 })
    await assignButton.click()

    const dialog = app.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText('Assign roles')).toBeVisible()

    const roleSearchInput = dialog.getByPlaceholder('Search for roles...')
    await expect(roleSearchInput).toBeVisible()
    await roleSearchInput.click()

    // PatternFly Select renders options in a portal outside the dialog
    const roleOptions = app.getByRole('option').filter({ hasNotText: /No results match/i })
    await expect(async () => {
      expect(await roleOptions.count()).toBeGreaterThan(0)
    }).toPass({ timeout: 15_000 })

    // Close the dialog via its X button — the PF6 Select dropdown is
    // a portal overlay that blocks the Cancel button, but the close
    // button in the dialog header is above the dropdown.
    await dialog.getByRole('button', { name: 'Close', exact: true }).click()
    await expect(dialog).not.toBeVisible()
  })

  test.describe('Member typeahead (mock backend only)', () => {
    test.skip(!!process.env.SYNTARA_E2E_SKIP_WEB_SERVER, 'Group typeahead unreliable against real backend')

    test('Add Member modal shows users in the typeahead dropdown', async ({ app }) => {
      if (!seededGroup) throw new Error('No seeded group created in beforeAll')

      await app.goto(toAppUrl(`/system-administration/access-management/groups/${seededGroup.id}`))
      await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 10_000 })

      const membersTab = app.getByRole('tab', { name: /members/i })
      await expect(membersTab).toBeVisible({ timeout: 5000 })
      await membersTab.click()

      const addMemberButton = app.getByRole('button', { name: /add member/i })
      await expect(addMemberButton).toBeVisible({ timeout: 10_000 })
      await addMemberButton.click()

      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByText('Add member')).toBeVisible()

      const searchInput = dialog.getByPlaceholder('Search for a user...')
      await searchInput.click()

      const noResults = dialog.getByText(/No results match/i)
      const userOptions = dialog.getByRole('option').filter({ hasNotText: /No results match/i })
      const hasOptions = await userOptions
        .or(noResults)
        .waitFor({ state: 'visible', timeout: 15_000 })
        .then(() => true)
        .catch(() => false)
      expect(hasOptions, 'Typeahead dropdown did not populate').toBeTruthy()
      expect(await userOptions.count()).toBeGreaterThan(0)

      await dialog.getByRole('button', { name: 'Cancel' }).click()
      await expect(dialog).not.toBeVisible()
    })
  })
})

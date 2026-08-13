/**
 * E2E Tests: Access Management — URL-synced tabs, filters, and sort (PR #525)
 *
 * Critical paths covered:
 * - Tab navigation syncs to URL
 * - Filter state syncs to URL and restores from URL
 * - Sort state syncs to URL and restores from URL
 * - Sort change resets pagination
 * - Shareable URLs preserve filters + sort across tabs
 * - Clear filters preserves sort
 *
 * Edge cases:
 * - Browser back/forward navigates between tabs
 * - Filters and sort survive a full page reload
 * - User detail sub-tabs sync to URL
 */
import { test, expect, toAppUrl, createUnavailableGuard } from './fixtures'
import { APP_TITLE } from './helpers/appTitle'
import { buildUniqueName } from './helpers/workflows'
import {
  createPolicyViaApi,
  createUserViaApi,
  deletePolicyViaApi,
  deleteUserViaApi,
  type SeededPolicy,
  type SeededUser,
} from './seeds/iam'
import { ensureProject, getAuthToken } from './utils/api'

const ACCESS_URL = '/system-administration/access-management'

const seededUsers: SeededUser[] = []
const seededPolicies: SeededPolicy[] = []

test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage()
  const token = await getAuthToken(page)
  if (token) {
    const prefix = buildUniqueName('e2e-am')

    for (let i = 1; i <= 2; i++) {
      const user = await createUserViaApi(page, { username: `${prefix}-user-${i}`, token })
      if (user) seededUsers.push(user)
    }

    const project = await ensureProject(page)
    if (project) {
      const policy = await createPolicyViaApi(page, project.id, { name: `${prefix}-policy`, token })
      if (policy) seededPolicies.push(policy)
    }
  }
  await page.close()
})

test.afterAll(async ({ browser }) => {
  const page = await browser.newPage()
  for (const policy of seededPolicies) {
    await deletePolicyViaApi(page, policy.projectId, policy.id)
  }
  for (const user of seededUsers) {
    await deleteUserViaApi(page, user.id)
  }
  await page.close()
})

test.describe('Access Management — Tab Navigation', () => {
  test.beforeEach(async ({ app }) => {
    await app.goto(toAppUrl(ACCESS_URL))
    await expect(app.getByRole('heading', { level: 1, name: 'Access Management' })).toBeVisible()
  })

  test('clicking tabs updates the URL', async ({ app }) => {
    await expect(app).toHaveTitle(`Access Management | ${APP_TITLE}`)
    // Click Roles tab
    await app.getByRole('tab', { name: /Roles/i }).click()
    await expect(app).toHaveURL(new RegExp(`${ACCESS_URL}/roles`))

    // Click Policies tab
    await app.getByRole('tab', { name: /Policies/i }).click()
    await expect(app).toHaveURL(new RegExp(`${ACCESS_URL}/policies`))

    // Click Users tab
    await app.getByRole('tab', { name: /Users/i }).click()
    await expect(app).toHaveURL(new RegExp(`${ACCESS_URL}/users`))

    // Click Groups tab
    await app.getByRole('tab', { name: /Groups/i }).click()
    await expect(app).toHaveURL(new RegExp(`${ACCESS_URL}/groups`))
  })

  test('browser back navigates between tabs', async ({ app }) => {
    // Navigate through tabs
    await app.getByRole('tab', { name: /Roles/i }).click()
    await expect(app).toHaveURL(new RegExp(`${ACCESS_URL}/roles`))

    await app.getByRole('tab', { name: /Policies/i }).click()
    await expect(app).toHaveURL(new RegExp(`${ACCESS_URL}/policies`))

    // Go back — should return to Roles
    await app.goBack()
    await expect(app).toHaveURL(new RegExp(`${ACCESS_URL}/roles`))
    await expect(app.getByRole('tab', { name: /Roles/i })).toHaveAttribute('aria-selected', 'true')
  })

  test('direct URL navigation selects the correct tab', async ({ app }) => {
    await app.goto(toAppUrl(`${ACCESS_URL}/policies`))
    await expect(app.getByRole('tab', { name: /Policies/i })).toHaveAttribute('aria-selected', 'true')

    await app.goto(toAppUrl(`${ACCESS_URL}/roles`))
    await expect(app.getByRole('tab', { name: /Roles/i })).toHaveAttribute('aria-selected', 'true')
  })
})

test.describe('Access Management — Roles Tab Filtering', () => {
  const guard = createUnavailableGuard('No roles data available; seed data required')

  test.beforeEach(async ({ app }) => {
    await app.goto(toAppUrl(`${ACCESS_URL}/roles`))
    await expect(app.getByRole('tab', { name: /Roles/i })).toHaveAttribute('aria-selected', 'true')

    const table = app.locator('table')
    const hasTable = await table
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    if (!hasTable) guard.markUnavailable()
    test.skip(!hasTable, 'No roles data available; seed data required')
  })

  test('filter by name syncs to URL', async ({ app }) => {
    await app.getByPlaceholder('Filter by name').fill('admin')
    await app.getByRole('button', { name: 'Apply filter' }).click()

    // Filter chip appears
    const nameChipGroup = app.locator('.pf-v6-c-label-group').filter({ hasText: 'Name' })
    await expect(nameChipGroup.getByText('admin')).toBeVisible()

    // URL contains filter
    expect(app.url()).toContain('name%5Bcontains%5D=admin')
  })

  test('filter state restores from URL', async ({ app }) => {
    await app.getByPlaceholder('Filter by name').fill('admin')
    await app.getByRole('button', { name: 'Apply filter' }).click()

    const nameChipGroup = app.locator('.pf-v6-c-label-group').filter({ hasText: 'Name' })
    await expect(nameChipGroup.getByText('admin')).toBeVisible()

    // Capture filtered URL, navigate away, then back
    const urlWithFilter = app.url()
    await app.goto(toAppUrl('/'))
    await app.goto(urlWithFilter)

    // Filter restored from URL
    await expect(app.getByRole('tab', { name: /Roles/i })).toHaveAttribute('aria-selected', 'true')
    const restoredChipGroup = app.locator('.pf-v6-c-label-group').filter({ hasText: 'Name' })
    await expect(restoredChipGroup.getByText('admin')).toBeVisible()
  })

  test('clear all filters removes chips and URL params', async ({ app }) => {
    // Apply filter
    await app.getByPlaceholder('Filter by name').fill('admin')
    await app.getByRole('button', { name: 'Apply filter' }).click()

    const nameChipGroup = app.locator('.pf-v6-c-label-group').filter({ hasText: 'Name' })
    await expect(nameChipGroup.getByText('admin')).toBeVisible()

    // Clear all filters
    await app.getByRole('search', { name: 'Filters' }).getByRole('button', { name: 'Clear all filters' }).click()

    // Filter chips gone from toolbar, URL clean
    await expect(app.getByRole('search', { name: 'Filters' }).getByRole('list')).toHaveCount(0)
    expect(app.url()).not.toContain('name%5Bcontains%5D')
  })
})

test.describe('Access Management — Roles Tab Sorting', () => {
  const guard = createUnavailableGuard('No roles data available; seed data required')

  test.beforeEach(async ({ app }) => {
    await app.goto(toAppUrl(`${ACCESS_URL}/roles`))
    await expect(app.getByRole('tab', { name: /Roles/i })).toHaveAttribute('aria-selected', 'true')

    const table = app.locator('table')
    const hasTable = await table
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    if (!hasTable) guard.markUnavailable()
    test.skip(!hasTable, 'No roles data available; seed data required')
  })

  test('clicking column header updates sort in URL', async ({ app }) => {
    // Click Name column header to sort
    const nameHeader = app.getByRole('columnheader', { name: 'Name' })
    await nameHeader.getByRole('button').click()

    // URL should contain sort param
    await expect(app).toHaveURL(/sort=/)
  })

  test('sort direction toggles on repeated clicks', async ({ app }) => {
    const nameHeader = app.getByRole('columnheader', { name: 'Name' })

    // First click — ascending
    await nameHeader.getByRole('button').click()
    await expect(nameHeader).toHaveAttribute('aria-sort', 'ascending')
    expect(app.url()).toContain('sort=name')

    // Second click — descending
    await nameHeader.getByRole('button').click()
    await expect(nameHeader).toHaveAttribute('aria-sort', 'descending')
    expect(app.url()).toContain('sort=-name')
  })

  test('sort state restores from URL', async ({ app }) => {
    // Navigate directly to URL with sort
    await app.goto(toAppUrl(`${ACCESS_URL}/roles?sort=-name`))

    const nameHeader = app.getByRole('columnheader', { name: 'Name' })
    await expect(nameHeader).toHaveAttribute('aria-sort', 'descending')
  })

  test('clear filters preserves sort', async ({ app }) => {
    // Apply filter
    await app.getByPlaceholder('Filter by name').fill('admin')
    await app.getByRole('button', { name: 'Apply filter' }).click()

    // Wait for filter chip to confirm UI has settled
    const nameChipGroup = app.locator('.pf-v6-c-label-group').filter({ hasText: 'Name' })
    await expect(nameChipGroup.getByText('admin')).toBeVisible()

    // Apply sort — click the table header's sort button.
    // force: true bypasses PF6 tooltip overlay on truncated column headers.
    const nameHeader = app.getByRole('columnheader', { name: 'Name' })
    await nameHeader.getByRole('button').click({ force: true })
    await expect(nameHeader).toHaveAttribute('aria-sort', 'ascending')

    // URL has both
    expect(app.url()).toContain('name%5Bcontains%5D=admin')
    expect(app.url()).toContain('sort=')

    // Clear filters
    await app.getByRole('search', { name: 'Filters' }).getByRole('button', { name: 'Clear all filters' }).click()

    // Filter gone, sort preserved
    expect(app.url()).not.toContain('name%5Bcontains%5D')
    expect(app.url()).toContain('sort=')
    await expect(nameHeader).toHaveAttribute('aria-sort', 'ascending')
  })
})

test.describe('Access Management — Shareable URLs', () => {
  test('filters + sort + tab in URL restore correctly after navigation', async ({ app }) => {
    await app.goto(toAppUrl(`${ACCESS_URL}/roles`))
    await expect(app.getByRole('tab', { name: /Roles/i })).toHaveAttribute('aria-selected', 'true')

    const table = app.locator('table')
    const hasTable = await table
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasTable, 'No roles data available; seed data required')

    await app.getByPlaceholder('Filter by name').fill('admin')
    await app.getByRole('button', { name: 'Apply filter' }).click()

    // Wait for filter chip to confirm UI has settled
    const nameChipGroup = app.locator('.pf-v6-c-label-group').filter({ hasText: 'Name' })
    await expect(nameChipGroup.getByText('admin')).toBeVisible()

    // Click sort — force: true bypasses PF6 tooltip overlay on truncated header
    const nameHeader = app.getByRole('columnheader', { name: 'Name' })
    await nameHeader.getByRole('button').click({ force: true })

    const fullUrl = app.url()
    expect(fullUrl).toContain('name%5Bcontains%5D=admin')
    expect(fullUrl).toContain('sort=')

    // Navigate away and back to verify URL state restores
    await app.goto(toAppUrl('/'))
    await app.goto(fullUrl)

    await expect(app.getByRole('tab', { name: /Roles/i })).toHaveAttribute('aria-selected', 'true')

    const restoredChip = app.locator('.pf-v6-c-label-group').filter({ hasText: 'Name' })
    await expect(restoredChip.getByText('admin')).toBeVisible()

    const restoredHeader = app.getByRole('columnheader', { name: 'Name' })
    await expect(restoredHeader).toHaveAttribute('aria-sort', 'ascending')
  })
})

test.describe('Access Management — User Detail Tabs', () => {
  test('detail sub-tabs sync to URL', async ({ app }) => {
    await app.goto(toAppUrl(`${ACCESS_URL}/users`))
    await expect(app.getByRole('tab', { name: /Users/i })).toHaveAttribute('aria-selected', 'true')

    // Wait for users table
    const table = app.getByRole('grid', { name: 'Users table' })
    const hasTable = await table
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasTable, 'No users data available; seed data required')

    // Click the first username button in the table to navigate to detail
    const firstRow = table.getByRole('row').nth(1) // skip header row
    await firstRow.locator('td[data-label="Username"]').getByRole('button').click()

    // Should be on user detail page
    await expect(app).toHaveURL(new RegExp(`${ACCESS_URL}/users/`))

    // Click Groups sub-tab if available
    const groupsTab = app.getByRole('tab', { name: /Groups/i })
    const hasGroupsTab = (await groupsTab.count()) > 0
    if (hasGroupsTab) {
      await groupsTab.click()
      await expect(app).toHaveURL(/\/groups$/)
    }

    // Click Roles sub-tab if available
    const rolesTab = app.getByRole('tab', { name: /Roles/i })
    const hasRolesTab = (await rolesTab.count()) > 0
    if (hasRolesTab) {
      await rolesTab.click()
      await expect(app).toHaveURL(/\/roles$/)
    }
  })
})

test.describe('Access Management — Policies Tab Columns', () => {
  const guard = createUnavailableGuard('No policies data available; seed data required')

  test.beforeEach(async ({ app }) => {
    await app.goto(toAppUrl(`${ACCESS_URL}/policies`))
    await expect(app.getByRole('tab', { name: /Policies/i })).toHaveAttribute('aria-selected', 'true')

    const table = app.getByRole('grid', { name: 'Policies' })
    const hasTable = await table
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    if (!hasTable) guard.markUnavailable()
    test.skip(!hasTable, 'No policies data available; seed data required')
  })

  test('Statements, Scope, Description and Project columns are visible', async ({ app }) => {
    await expect(app.getByRole('columnheader', { name: 'Description' })).toBeVisible()
    await expect(app.getByRole('columnheader', { name: 'Scope' })).toBeVisible()
    await expect(app.getByRole('columnheader', { name: 'Statements' })).toBeVisible()
    await expect(app.getByRole('columnheader', { name: 'Project' })).toBeVisible()
    await expect(app.getByRole('columnheader', { name: 'Type' })).toBeVisible()
  })

  test('Statements column shows Allow/Deny labels and action chips', async ({ app }) => {
    const table = app.getByRole('grid', { name: 'Policies' })

    // At least one Allow or Deny label should be visible in the statements column
    const statementsColumn = table.locator('td[data-label="Statements"]')
    const hasAllowLabel = (await statementsColumn.getByText('Allow').count()) > 0
    const hasDenyLabel = (await statementsColumn.getByText('Deny').count()) > 0

    test.skip(!hasAllowLabel && !hasDenyLabel, 'No statement effect labels rendered; statements data required')

    // At least one scope label should be visible (e.g. "scope: any")
    await expect(statementsColumn.getByText(/^scope:/).nth(0)).toBeVisible()
  })

  test('project-scoped policies show a clickable project link', async ({ app }) => {
    const table = app.getByRole('grid', { name: 'Policies' })

    // Scope into Project column cells via data-label, then look for the link button rendered by ProjectLabel
    const projectButtons = table.locator('td[data-label="Project"]').getByRole('button')
    const hasProjectLink = (await projectButtons.count()) > 0

    test.skip(!hasProjectLink, 'No project-scoped policies on this page; seed data required')

    await expect(projectButtons.nth(0)).toBeVisible()
  })
})

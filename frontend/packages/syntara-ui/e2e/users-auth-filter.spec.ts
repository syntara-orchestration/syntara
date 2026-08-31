/**
 * Test UI-34: Users Table — Authentication Method Filter
 *
 * Critical paths covered:
 * - Filtering by "Local" shows only local users
 * - Filtering by "AAP" shows only federated users
 * - Email and Authentication filters can be combined to narrow results
 * - Filters are clearable and the table restores to its unfiltered state
 *
 * Uses Playwright route interception to mock API responses.
 * Read-only tests — no cleanup required.
 */
import { test, expect, toAppUrl } from './fixtures'
import { AAP_AUTH_PROVIDER } from './fixtures/mock-oidc-idps'
import { ACCESS_URL, fulfill, mockAuthProviders, mockUsersWithAuthSources } from './utils/mockData'

function filterUsers(authSource: string | null, emailContains: string | null) {
  let filtered = mockUsersWithAuthSources.resources
  if (authSource) {
    filtered = filtered.filter((u) => u.auth_sources.includes(authSource))
  }
  if (emailContains) {
    filtered = filtered.filter((u) => u.email.includes(emailContains))
  }
  return { resources: filtered, next: null, prev: null, total: filtered.length }
}

test.describe('Users Table — Authentication Method Filter (UI-34)', () => {
  test.beforeEach(async ({ app }) => {
    await app.route('**/api/v1/users**', (route) => {
      const url = new URL(route.request().url())
      return route.fulfill(
        fulfill(filterUsers(url.searchParams.get('auth_source'), url.searchParams.get('email[contains]')))
      )
    })
    await mockAuthProviders(app, { resources: [AAP_AUTH_PROVIDER] })
    await app.goto(toAppUrl(ACCESS_URL))
    await expect(app.getByRole('grid', { name: 'Users' })).toBeVisible()
  })

  test('filtering by Local or AAP shows only matching users', async ({ app }) => {
    const toolbar = app.getByRole('search', { name: 'Filters' })
    const table = app.getByRole('grid', { name: 'Users' })
    const dataRows = table.getByRole('row').filter({ hasNot: app.locator('th') })

    // Switch to Authentication filter field
    await toolbar.getByRole('button', { name: 'Username' }).click()
    await app.getByRole('option', { name: 'Authentication' }).click()

    // Filter by "Local"
    await app.getByRole('button', { name: 'Filter by authentication' }).click()
    await app.getByRole('option', { name: 'Local' }).click()

    const authChipGroup = toolbar.getByRole('list', { name: 'Authentication' })
    await expect(authChipGroup.getByText('Local')).toBeVisible()
    await expect(app).toHaveURL(/auth_source=Local/)

    // Verify only local users are shown
    await expect(dataRows).toHaveCount(2)
    const localRows = await dataRows.all()
    for (const row of localRows) {
      await expect(row.getByText('Local', { exact: true })).toBeVisible()
    }

    // Clear Local chip and filter by "AAP"
    await authChipGroup.getByRole('button', { name: 'Close Local' }).click()

    await app.getByRole('button', { name: 'Filter by authentication' }).click()
    await app.getByRole('option', { name: 'AAP' }).click()

    await expect(authChipGroup.getByText('AAP')).toBeVisible()
    await expect(app).toHaveURL(/auth_source=AAP/)

    // Verify only federated users are shown
    await expect(dataRows).toHaveCount(1)
    await expect(dataRows.getByText('AAP', { exact: true })).toBeVisible()
  })

  test('combining Email and Authentication filters narrows results', async ({ app }) => {
    const toolbar = app.getByRole('search', { name: 'Filters' })
    const table = app.getByRole('grid', { name: 'Users' })

    // Apply Email filter
    await toolbar.getByRole('button', { name: 'Username' }).click()
    await app.getByRole('option', { name: 'Email' }).click()
    await app.getByPlaceholder('Filter by email').fill('admin@example.com')
    await app.getByRole('button', { name: 'Apply filter' }).click()

    const emailChipGroup = toolbar.getByRole('list', { name: 'Email' })
    await expect(emailChipGroup.getByText('admin@example.com')).toBeVisible()

    // Add Authentication filter
    await toolbar.getByRole('button', { name: 'Email', exact: true }).click()
    await app.getByRole('option', { name: 'Authentication' }).click()
    await app.getByRole('button', { name: 'Filter by authentication' }).click()
    await app.getByRole('option', { name: 'Local' }).click()

    // Verify both filter chips are active
    await expect(emailChipGroup.getByText('admin@example.com')).toBeVisible()
    const authChipGroup = toolbar.getByRole('list', { name: 'Authentication' })
    await expect(authChipGroup.getByText('Local')).toBeVisible()

    // Verify URL contains both filters
    await expect(app).toHaveURL(/email/)
    await expect(app).toHaveURL(/auth_source=Local/)

    // Verify narrowed results
    const dataRows = table.getByRole('row').filter({ hasNot: app.locator('th') })
    await expect(dataRows).toHaveCount(1)
    await expect(dataRows.getByText('admin@example.com')).toBeVisible()
    await expect(dataRows.getByText('Local', { exact: true })).toBeVisible()
  })

  test('clearing filters restores unfiltered results', async ({ app }) => {
    const toolbar = app.getByRole('search', { name: 'Filters' })
    const table = app.getByRole('grid', { name: 'Users' })
    const dataRows = table.getByRole('row').filter({ hasNot: app.locator('th') })

    // Verify initial unfiltered state shows all users
    await expect(dataRows).toHaveCount(3)

    // Apply Email filter
    await toolbar.getByRole('button', { name: 'Username' }).click()
    await app.getByRole('option', { name: 'Email' }).click()
    await app.getByPlaceholder('Filter by email').fill('admin@example.com')
    await app.getByRole('button', { name: 'Apply filter' }).click()

    const emailChipGroup = toolbar.getByRole('list', { name: 'Email' })
    await expect(emailChipGroup.getByText('admin@example.com')).toBeVisible()

    // Add Authentication filter
    await toolbar.getByRole('button', { name: 'Email', exact: true }).click()
    await app.getByRole('option', { name: 'Authentication' }).click()
    await app.getByRole('button', { name: 'Filter by authentication' }).click()
    await app.getByRole('option', { name: 'Local' }).click()

    const authChipGroup = toolbar.getByRole('list', { name: 'Authentication' })
    await expect(authChipGroup.getByText('Local')).toBeVisible()

    // Verify filtered to single result
    await expect(dataRows).toHaveCount(1)

    // Clear the authentication filter chip
    await authChipGroup.getByRole('button', { name: 'Close Local' }).click()

    // Verify auth filter removed, email filter remains
    await expect(authChipGroup).not.toBeVisible()
    await expect(app).not.toHaveURL(/auth_source=/)
    await expect(emailChipGroup.getByText('admin@example.com')).toBeVisible()

    // Clear the email filter chip
    await emailChipGroup.getByRole('button', { name: 'Close admin@example.com' }).click()

    // Verify all filters removed and all results restored
    await expect(emailChipGroup).not.toBeVisible()
    await expect(app).not.toHaveURL(/email/)
    await expect(dataRows).toHaveCount(3)
  })
})

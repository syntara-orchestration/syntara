import { createUnavailableGuard, test, expect, toAppUrl } from './fixtures'
import { buildUniqueName } from './helpers/workflows'
import { createIntegrationViaApi, deleteIntegrationViaApi, type SeededIntegration } from './seeds/resources'
import { getAuthToken } from './utils/api'

const seededIntegrations: SeededIntegration[] = []

test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage()
  const token = await getAuthToken(page)
  if (token) {
    const prefix = buildUniqueName('e2e-intfilt')
    for (let i = 1; i <= 12; i++) {
      const name = i === 1 ? `${prefix}-copilot` : `${prefix}-integration-${i}`
      const integration = await createIntegrationViaApi(page, { name, token })
      if (integration) seededIntegrations.push(integration)
    }
  }
  await page.close()
})

test.afterAll(async ({ browser }) => {
  const page = await browser.newPage()
  for (const integration of seededIntegrations) {
    await deleteIntegrationViaApi(page, integration.id)
  }
  await page.close()
})

test.describe('Integration Filtering', () => {
  const guard = createUnavailableGuard('No integration data available; seed data required')

  test.beforeEach(async ({ app }) => {
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()
    const grid = app.getByRole('grid', { name: 'Integrations table' })
    const hasGrid = await grid
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    if (!hasGrid) guard.markUnavailable()
    test.skip(!hasGrid, 'No integration data available; seed data required')
  })

  test('keyword search: filter by integration name', async ({ app }) => {
    // Navigate to integrations page
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()

    // Wait for table to load
    const table = app.getByRole('grid', { name: 'Integrations table' })
    await expect(table).toBeVisible()

    // Act - Search for "copilot" using name filter
    const nameFilterInput = app.getByPlaceholder('Filter by name')
    await nameFilterInput.fill('copilot')
    await app.getByRole('button', { name: 'Apply filter' }).click()

    // Assert - Filter chip displayed
    const nameChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })
    await expect(nameChipGroup).toBeVisible()
    await expect(nameChipGroup.getByText('copilot')).toBeVisible()

    // Verify URL contains filter
    await expect(app).toHaveURL(/name%5Bcontains%5D=copilot/)

    // Verify filtered results exist (skip if filter matched nothing — no mock seed data)
    const dataRow = table.locator('tbody tr:first-child')
    const hasResults = await dataRow
      .waitFor({ state: 'visible', timeout: 3000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasResults, 'No integrations matching "copilot" filter; seed data required')
  })

  test('name filter: apply and clear name filter', async ({ app }) => {
    // Navigate to integrations
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()

    // Act - Apply name filter
    await app.getByPlaceholder('Filter by name').fill('slack')
    await app.getByRole('button', { name: 'Apply filter' }).click()

    // Assert - Filter chip displayed
    const nameChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })
    await expect(nameChipGroup.getByText('slack')).toBeVisible()

    // Verify URL
    await expect(app).toHaveURL(/name%5Bcontains%5D=slack/)

    // Act - Clear filter using chip close button
    await nameChipGroup.getByRole('listitem', { name: 'slack' }).getByRole('button', { name: /close/i }).click()

    // Assert - Filter removed
    await expect(nameChipGroup).not.toBeVisible()
    await expect(app).not.toHaveURL(/name%5Bcontains%5D/)
  })

  test('status filter: switch between status values', async ({ app }) => {
    // Navigate to integrations
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()

    const table = app.getByRole('grid', { name: 'Integrations table' })
    await expect(table).toBeVisible()

    // Act - Switch to Status field and apply "Available" status filter
    const fieldSelector = app
      .getByRole('search', { name: 'Filters' })
      .getByRole('button', { name: 'Name', exact: true })
    await fieldSelector.click()
    await app.getByRole('option', { name: 'Status' }).click()
    await app.getByRole('button', { name: 'Filter by status' }).click()
    await app.getByRole('option', { name: 'Available' }).click()

    // Assert - Status filter chip displayed
    const statusChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Status' })
    await expect(statusChipGroup).toBeVisible()
    await expect(statusChipGroup.getByText('Available')).toBeVisible()

    // Verify URL
    await expect(app).toHaveURL(/status=available/)

    // Verify filtered results exist (skip if filter matched nothing)
    const dataRow = table.locator('tbody tr:first-child')
    const hasAvailable = await dataRow
      .waitFor({ state: 'visible', timeout: 3000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasAvailable, 'No integrations with "Available" status; seed data required')

    // Act - Switch to "Error" status (replaces "Available")
    await app.getByRole('search', { name: 'Filters' }).getByRole('button', { name: 'Available', exact: true }).click()
    await app.getByRole('option', { name: 'Error' }).click()

    // Assert - Status filter updated to "Error"
    await expect(statusChipGroup.getByText('Error')).toBeVisible()
    await expect(statusChipGroup.getByText('Available')).not.toBeVisible()

    // Verify URL updated
    await expect(app).toHaveURL(/status=error/)
    await expect(app).not.toHaveURL(/status=available/)

    // Act - Remove status filter
    await statusChipGroup.getByRole('listitem', { name: 'Error' }).getByRole('button', { name: /close/i }).click()

    // Assert - Status filter removed
    await expect(statusChipGroup).not.toBeVisible()
    await expect(app).not.toHaveURL(/status=/)
  })

  test('combined filters: name + status + integration type', async ({ app }) => {
    // Navigate to integrations
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()

    // Act - Apply name filter
    await app.getByPlaceholder('Filter by name').fill('integration')
    await app.getByRole('button', { name: 'Apply filter' }).click()

    // Assert - Name filter applied
    const nameChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })
    await expect(nameChipGroup.getByText('integration')).toBeVisible()
    await expect(app).toHaveURL(/name%5Bcontains%5D=integration/)

    // Act - Switch to Status and add status filter
    const fieldSelector = app
      .getByRole('search', { name: 'Filters' })
      .getByRole('button', { name: 'Name', exact: true })
    await fieldSelector.click()
    await app.getByRole('option', { name: 'Status' }).click()
    await app.getByRole('button', { name: 'Filter by status' }).click()
    await app.getByRole('option', { name: 'Error' }).click()

    // Assert - Status filter applied
    const statusChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Status' })
    await expect(statusChipGroup.getByText('Error')).toBeVisible()
    await expect(app).toHaveURL(/status=error/)

    // Act - Switch to Integration type and add filter (re-query field selector)
    const fieldSelector2 = app
      .getByRole('search', { name: 'Filters' })
      .getByRole('button', { name: 'Status', exact: true })
    await fieldSelector2.click()
    await app.getByRole('option', { name: 'Integration type' }).click()
    await app.getByRole('button', { name: 'Filter by integration type' }).click()
    await app.getByRole('option', { name: 'MCP Server' }).click()

    // Assert - Integration type filter applied
    const typeChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Integration type' })
    await expect(typeChipGroup.getByText('MCP Server')).toBeVisible()
    await expect(app).toHaveURL(/provider_type=mcp/)

    // Assert - All three filters active
    await expect(nameChipGroup.getByText('integration')).toBeVisible()
    await expect(statusChipGroup.getByText('Error')).toBeVisible()
    await expect(typeChipGroup.getByText('MCP Server')).toBeVisible()

    // Verify URL contains all filters
    await expect(app).toHaveURL(/name%5Bcontains%5D=integration/)
    await expect(app).toHaveURL(/status=error/)
    await expect(app).toHaveURL(/provider_type=mcp/)

    // Act - Clear all filters
    await app.getByRole('search', { name: 'Filters' }).getByRole('button', { name: 'Clear all filters' }).click()

    // Assert - All filters removed
    await expect(app.getByRole('search', { name: 'Filters' }).getByRole('list')).toHaveCount(0)
    await expect(app).not.toHaveURL(/name%5Bcontains%5D/)
    await expect(app).not.toHaveURL(/status=/)
    await expect(app).not.toHaveURL(/provider_type=/)
  })

  test('shareable URLs: filters restored from URL', async ({ app, context }) => {
    // Navigate to integrations and apply filters
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()

    // Apply name filter
    await app.getByPlaceholder('Filter by name').fill('bot')
    await app.getByRole('button', { name: 'Apply filter' }).click()

    // Apply status filter
    const fieldSelector = app
      .getByRole('search', { name: 'Filters' })
      .getByRole('button', { name: 'Name', exact: true })
    await fieldSelector.click()
    await app.getByRole('option', { name: 'Status' }).click()
    await app.getByRole('button', { name: 'Filter by status' }).click()
    await app.getByRole('option', { name: 'Available' }).click()

    // Verify filters applied
    const nameChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })
    await expect(nameChipGroup.getByText('bot')).toBeVisible()
    const statusChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Status' })
    await expect(statusChipGroup.getByText('Available')).toBeVisible()

    // Capture URL with filters
    const urlWithFilters = app.url()
    await expect(app).toHaveURL(/name%5Bcontains%5D=bot/)
    await expect(app).toHaveURL(/status=available/)

    // Act - Open URL in new tab (simulate sharing URL)
    const newPage = await context.newPage()
    await newPage.goto(urlWithFilters)

    // Assert - Filters restored in new tab
    await expect(newPage.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()
    const newPageNameChipGroup = newPage.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })
    await expect(newPageNameChipGroup.getByText('bot')).toBeVisible()
    const newPageStatusChipGroup = newPage
      .getByRole('search', { name: 'Filters' })
      .getByRole('list', { name: 'Status' })
    await expect(newPageStatusChipGroup.getByText('Available')).toBeVisible()

    // Cleanup
    await newPage.close()
  })

  test('shareable URLs: clear filters and share clean URL', async ({ app, context }) => {
    // Navigate to integrations with filters
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()

    // Apply filter
    await app.getByPlaceholder('Filter by name').fill('test')
    await app.getByRole('button', { name: 'Apply filter' }).click()
    const nameChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })
    await expect(nameChipGroup.getByText('test')).toBeVisible()
    await expect(app).toHaveURL(/name%5Bcontains%5D/)

    // Act - Clear filters (use toolbar button, not pagination button)
    await app.getByRole('search', { name: 'Filters' }).getByRole('button', { name: 'Clear all filters' }).click()

    // Assert - URL no longer contains filter params
    await expect(app).not.toHaveURL(/name%5Bcontains%5D/)
    await expect(app).not.toHaveURL(/status=/)

    // Act - Share clean URL in new tab
    const cleanUrl = app.url()
    const newPage = await context.newPage()
    await newPage.goto(cleanUrl)

    // Assert - No filters in new tab
    await expect(newPage.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()
    await expect(newPage.getByRole('search', { name: 'Filters' }).getByRole('list')).toHaveCount(0)

    // Cleanup
    await newPage.close()
  })

  test('filter state persists across navigation (URL-based)', async ({ app }) => {
    // Navigate to integrations and apply filter
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()

    await app.getByPlaceholder('Filter by name').fill('slack')
    await app.getByRole('button', { name: 'Apply filter' }).click()
    const nameChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })
    await expect(nameChipGroup.getByText('slack')).toBeVisible()

    // Capture URL with filter
    const urlWithFilter = app.url()
    await expect(app).toHaveURL(/name%5Bcontains%5D=slack/)

    // Act - Navigate to a different page
    await app.goto(toAppUrl('/'))

    // Act - Navigate back to the saved URL with filter
    await app.goto(urlWithFilter)

    // Assert - Filter state restored from URL
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()
    const restoredNameChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })
    await expect(restoredNameChipGroup.getByText('slack')).toBeVisible()

    // Verify URL still contains filter
    await expect(app).toHaveURL(/name%5Bcontains%5D=slack/)
  })

  test('individual filter chips can be removed', async ({ app }) => {
    // Navigate and apply multiple filters
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()

    // Apply name filter
    await app.getByPlaceholder('Filter by name').fill('monitor')
    await app.getByRole('button', { name: 'Apply filter' }).click()

    // Apply status filter
    const fieldSelector = app
      .getByRole('search', { name: 'Filters' })
      .getByRole('button', { name: 'Name', exact: true })
    await fieldSelector.click()
    await app.getByRole('option', { name: 'Status' }).click()
    await app.getByRole('button', { name: 'Filter by status' }).click()
    await app.getByRole('option', { name: 'Available' }).click()

    // Verify both filters active
    const nameChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })
    await expect(nameChipGroup.getByText('monitor')).toBeVisible()
    const statusChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Status' })
    await expect(statusChipGroup.getByText('Available')).toBeVisible()

    // Act - Remove name filter chip
    await nameChipGroup.getByRole('listitem', { name: 'monitor' }).getByRole('button', { name: /close/i }).click()

    // Assert - Name filter removed, status filter remains
    await expect(nameChipGroup).not.toBeVisible()
    await expect(statusChipGroup.getByText('Available')).toBeVisible()

    // Assert - URL updated
    await expect(app).not.toHaveURL(/name%5Bcontains%5D/)
    await expect(app).toHaveURL(/status=available/)

    // Act - Remove status filter chip
    await statusChipGroup.getByRole('listitem', { name: 'Available' }).getByRole('button', { name: /close/i }).click()

    // Assert - All filters removed
    await expect(app.getByRole('search', { name: 'Filters' }).getByRole('list')).toHaveCount(0)
    await expect(app).not.toHaveURL(/status=/)
  })

  test('empty state shows when filters return no results', async ({ app }) => {
    // Navigate to integrations
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()

    // Wait for table to load
    await expect(app.getByRole('grid', { name: 'Integrations table' })).toBeVisible()

    // Apply filter with impossible name that will never match our mock data
    await app.getByPlaceholder('Filter by name').fill('ZZZZZ_NONEXISTENT_12345')
    await app.getByRole('button', { name: 'Apply filter' }).click()

    // Wait for filter chip to appear
    const nameChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })
    await expect(nameChipGroup).toBeVisible()

    // Assert - Empty state with "No results found" heading
    await expect(app.getByRole('heading', { name: 'No results found' })).toBeVisible()

    // Clear filters using button in empty state (not the toolbar button)
    await app.getByRole('button', { name: 'Clear all filters' }).last().click()

    // Assert - Filter removed, table visible again
    await expect(nameChipGroup).not.toBeVisible()
    await expect(app.getByRole('grid', { name: 'Integrations table' })).toBeVisible()
  })

  test('pagination works', async ({ app }) => {
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()
    const grid = app.getByRole('grid', { name: 'Integrations table' })
    await expect(grid).toBeVisible()

    const rowCount = await grid.getByRole('row').count()
    test.skip(rowCount < 6, 'Insufficient integration data for pagination; seed data required')

    // Skip if not enough data for pagination
    const nextButton = app.getByRole('button', { name: 'Go to next page' })
    const prevButton = app.getByRole('button', { name: 'Go to previous page' })
    const nextVisible = await nextButton
      .waitFor({ state: 'visible', timeout: 10_000 })
      .then(() => true)
      .catch(() => false)
    const hasPagination = nextVisible && (await nextButton.isEnabled().catch(() => false))
    test.skip(!hasPagination, 'Not enough integrations to trigger pagination')

    // Act - Navigate to page 2
    await expect(prevButton).toBeDisabled()
    await nextButton.click()

    // Wait for page 2 to load (prev button becomes enabled)
    await expect(prevButton).not.toBeDisabled()

    // Act - Go back to page 1
    await prevButton.click()

    // Assert - Back to first page
    if ((await prevButton.count()) > 0) {
      await expect(prevButton).toBeDisabled()
    }
  })

  test('full user flow: add filters → view results → clear filters', async ({ app }) => {
    // Navigate to integrations page
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()

    // Wait for table to load
    const table = app.getByRole('grid', { name: 'Integrations table' })
    await expect(table).toBeVisible()

    // Act - Apply name filter (use a term likely to match some integrations)
    const nameFilterInput = app.getByPlaceholder('Filter by name')
    await nameFilterInput.fill('integration')
    await app.getByRole('button', { name: 'Apply filter' }).click()

    // Assert - Active filter chip displayed
    const nameChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })
    await expect(nameChipGroup).toBeVisible()
    await expect(nameChipGroup.getByText('integration')).toBeVisible()

    // Verify URL contains filter
    await expect(app).toHaveURL(/name%5Bcontains%5D=integration/)

    // Act - Add status filter (switch to Status field and select "Available")
    const fieldSelector = app
      .getByRole('search', { name: 'Filters' })
      .getByRole('button', { name: 'Name', exact: true })
    await fieldSelector.click()
    await app.getByRole('option', { name: 'Status' }).click()
    await app.getByRole('button', { name: 'Filter by status' }).click()
    await app.getByRole('option', { name: 'Available' }).click()

    // Assert - Both filter chips displayed
    await expect(nameChipGroup.getByText('integration')).toBeVisible()
    const statusChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Status' })
    await expect(statusChipGroup).toBeVisible()
    await expect(statusChipGroup.getByText('Available')).toBeVisible()

    // Verify both filters in URL
    await expect(app).toHaveURL(/name%5Bcontains%5D=integration/)
    await expect(app).toHaveURL(/status=available/)

    // Act - Clear all filters (use first button in toolbar, not in empty state)
    await app.getByRole('search', { name: 'Filters' }).getByRole('button', { name: 'Clear all filters' }).click()

    // Assert - All filter chips removed
    await expect(app.getByRole('search', { name: 'Filters' }).getByRole('list')).toHaveCount(0)

    // Verify URL no longer contains filters
    await expect(app).not.toHaveURL(/name%5Bcontains%5D/)
    await expect(app).not.toHaveURL(/status=/)
  })
})

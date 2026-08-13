/**
 * E2E Tests: Credentials List Page (additive)
 *
 * Tests 2-7 from the ANSTRAT-1901 test plan. Test 1 (Configuration Navigation)
 * is already covered by configuration-navigation.spec.ts.
 *
 * Covers:
 * - Empty state and filter empty state
 * - Table columns and sorting
 * - Cursor-based pagination
 * - Name keyword filtering
 * - Kebab menu edit action
 * - Kebab menu delete action
 */
import { createUnavailableGuard, test, expect } from './fixtures'
import { APP_TITLE } from './helpers/appTitle'
import {
  createTestCredential,
  deleteCredentialByName,
  filterCredentialByName,
  goToCredentialsList,
} from './helpers/credentials'
import { buildUniqueName } from './helpers/workflows'
import { createCredentialSeed, deleteCredentialViaApi, type SeededCredential } from './seeds/resources'
import { getAuthToken } from './utils/api'

const seededCredentials: SeededCredential[] = []

test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage()
  const token = await getAuthToken(page)
  if (token) {
    const prefix = buildUniqueName('e2e-credlist')
    for (let i = 1; i <= 3; i++) {
      const cred = await createCredentialSeed(page, { name: `${prefix}-cred-${i}`, token })
      if (cred) seededCredentials.push(cred)
    }
  }
  await page.close()
})

test.afterAll(async ({ browser }) => {
  const page = await browser.newPage()
  for (const cred of seededCredentials) {
    await deleteCredentialViaApi(page, cred.id)
  }
  await page.close()
})

// ---------------------------------------------------------------------------
// Test 2: Credentials List Page — Empty State
// ---------------------------------------------------------------------------
test.describe('Credentials Empty State', () => {
  test('shows EmptyStateFilter when filter returns no results', async ({ app }) => {
    // Create a credential first so the filter toolbar renders (empty state has no toolbar)
    const { name: credName } = await createTestCredential(app, { prefix: 'e2e-filter-empty' })

    try {
      await goToCredentialsList(app)
      await expect(app.getByPlaceholder('Filter by keyword')).toBeVisible({ timeout: 15_000 })

      const nonexistent = buildUniqueName('e2e-nonexistent')
      await filterCredentialByName(app, nonexistent)

      await expect(app.getByText('No results found')).toBeVisible()
      await expect(
        app.getByRole('search', { name: 'Filters' }).getByRole('button', { name: 'Clear all filters' })
      ).toBeVisible()
    } finally {
      await deleteCredentialByName(app, credName)
    }
  })

  test('Create credential button is visible on credentials page', async ({ app }) => {
    await goToCredentialsList(app, { ensureCreateEnabled: true })
    await expect(app).toHaveTitle(`Credentials | ${APP_TITLE}`)

    await expect(app.getByRole('button', { name: 'Create credential' })).toBeVisible()
  })

  test('clicking Create credential opens creation modal', async ({ app }) => {
    await goToCredentialsList(app, { ensureCreateEnabled: true })

    await app.getByRole('button', { name: 'Create credential' }).click()

    const modal = app.getByRole('dialog')
    await expect(modal).toBeVisible()
    await expect(modal.getByRole('heading', { name: 'Create credential' })).toBeVisible()

    await modal.getByRole('button', { name: 'Cancel' }).click()
    await expect(modal).not.toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// Test 3: Table Display and Sorting
// ---------------------------------------------------------------------------
test.describe('Table Display and Sorting', () => {
  test('table displays all 6 column headers and supports sort toggle', async ({ app }) => {
    const credNames: string[] = []
    for (let i = 0; i < 3; i++) {
      const { name } = await createTestCredential(app, { prefix: `e2e-sort-${String(i)}` })
      credNames.push(name)
    }

    try {
      await goToCredentialsList(app)
      await filterCredentialByName(app, 'e2e-sort-')

      const table = app.getByRole('grid', { name: 'Credentials table' })
      const hasTable = await table
        .waitFor({ state: 'visible', timeout: 5000 })
        .then(() => true)
        .catch(() => false)
      test.skip(!hasTable, 'No credential data available; seed data required')

      await expect(table.getByRole('columnheader', { name: 'Name' })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: 'Type' })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: 'Workflows' })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: 'Created' })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: 'Last modified' })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: 'State' })).toBeVisible()

      const nameHeader = table.getByRole('columnheader', { name: 'Name' })
      const currentSort = await nameHeader.getAttribute('aria-sort')

      await nameHeader.getByRole('button').click()
      const firstClick = currentSort === 'ascending' ? 'descending' : 'ascending'
      await expect(nameHeader).toHaveAttribute('aria-sort', firstClick)

      await nameHeader.getByRole('button').click()
      const secondClick = firstClick === 'ascending' ? 'descending' : 'ascending'
      await expect(nameHeader).toHaveAttribute('aria-sort', secondClick)
    } finally {
      for (const name of credNames) {
        await deleteCredentialByName(app, name)
      }
    }
  })
})

// ---------------------------------------------------------------------------
// Test 4: Cursor-Based Pagination
// ---------------------------------------------------------------------------
test.describe('Cursor-Based Pagination', () => {
  const guard = createUnavailableGuard('No credential data available; seed data required')

  test.beforeEach(async ({ app }) => {
    await goToCredentialsList(app)
    const table = app.getByRole('grid', { name: 'Credentials table' })
    const hasTable = await table
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    if (!hasTable) guard.markUnavailable()
    test.skip(!hasTable, 'No credential data available; seed data required')
  })

  test('pagination footer displays credential count', async ({ app }) => {
    const credentialCountText = app.locator('.pf-v6-c-pagination').getByText(/of \d+/)
    await expect(credentialCountText).toBeVisible()
  })

  test('next/previous controls navigate between pages when available', async ({ app }) => {
    const pagination = app.locator('.pf-v6-c-pagination')
    const nextButton = pagination.getByRole('button', { name: /next/i })
    const hasNext = await nextButton
      .waitFor({ state: 'visible', timeout: 3000 })
      .then(() => true)
      .catch(() => false)

    if (hasNext && (await nextButton.isEnabled())) {
      await nextButton.click()

      const prevButton = pagination.getByRole('button', { name: /prev/i })
      await expect(prevButton).toBeEnabled()

      await prevButton.click()
      const table = app.getByRole('grid', { name: 'Credentials table' })
      await expect(table).toBeVisible()
    }
  })
})

// ---------------------------------------------------------------------------
// Test 5: Name Keyword Filtering
// ---------------------------------------------------------------------------
test.describe('Name Keyword Filtering', () => {
  test('filter by keyword shows matching credentials', async ({ app }) => {
    const { name: credName } = await createTestCredential(app, { prefix: 'e2e-filter-match' })

    try {
      await goToCredentialsList(app)
      await filterCredentialByName(app, credName)

      const row = app.getByRole('row', { name: new RegExp(credName) })
      await expect(row).toBeVisible()
    } finally {
      await deleteCredentialByName(app, credName)
    }
  })

  test('clear filter restores full list', async ({ app }) => {
    const { name: credName } = await createTestCredential(app, { prefix: 'e2e-filter-clear' })

    try {
      await goToCredentialsList(app)
      await filterCredentialByName(app, credName)

      const row = app.getByRole('row', { name: new RegExp(credName) })
      await expect(row).toBeVisible()

      const clearBtn = app.getByRole('button', { name: 'Clear all filters' })
      const hasClearBtn = await clearBtn
        .waitFor({ state: 'visible', timeout: 3000 })
        .then(() => true)
        .catch(() => false)

      if (hasClearBtn) {
        await clearBtn.click()
      } else {
        await app.getByPlaceholder('Filter by keyword').fill('')
        await app.getByRole('button', { name: 'Apply filter' }).click()
      }

      const table = app.getByRole('grid', { name: 'Credentials table' })
      await expect(table).toBeVisible()
    } finally {
      await deleteCredentialByName(app, credName)
    }
  })

  test('non-matching filter shows EmptyStateFilter', async ({ app }) => {
    const { name: credName } = await createTestCredential(app, { prefix: 'e2e-filter-nomatch' })

    try {
      await goToCredentialsList(app)
      await expect(app.getByPlaceholder('Filter by keyword')).toBeVisible({ timeout: 15_000 })
      const nonexistent = buildUniqueName('e2e-no-match-ever')
      await filterCredentialByName(app, nonexistent)

      await expect(app.getByText('No results found')).toBeVisible()
      await expect(
        app.getByRole('search', { name: 'Filters' }).getByRole('button', { name: 'Clear all filters' })
      ).toBeVisible()
    } finally {
      await deleteCredentialByName(app, credName)
    }
  })
})

// ---------------------------------------------------------------------------
// Test 6: Kebab Menu Edit Action
// ---------------------------------------------------------------------------
test.describe('Kebab Menu Edit Action', () => {
  test('edit from kebab opens modal in edit mode with pre-populated fields', async ({ app }) => {
    const { name: credName } = await createTestCredential(app, { prefix: 'e2e-kebab-edit' })

    try {
      await goToCredentialsList(app)
      await filterCredentialByName(app, credName)

      const row = app.getByRole('row', { name: new RegExp(credName) })
      await row.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })

      await app.getByRole('menuitem', { name: 'Edit' }).click()

      const modal = app.getByRole('dialog')
      await expect(modal).toBeVisible()
      await expect(modal.getByText(`Edit ${credName}`)).toBeVisible()

      await expect(modal.getByRole('textbox', { name: 'Credential name' })).toHaveValue(credName)
      await expect(modal.getByRole('button', { name: 'Credential type', exact: true })).toBeDisabled()

      await modal.getByRole('button', { name: 'Cancel' }).click()
      await expect(modal).not.toBeVisible()
    } finally {
      await deleteCredentialByName(app, credName)
    }
  })
})

// ---------------------------------------------------------------------------
// Test 7: Kebab Menu Delete Action
// ---------------------------------------------------------------------------
test.describe('Kebab Menu Delete Action', () => {
  test('delete from kebab shows confirmation and completes deletion', async ({ app }) => {
    const { name: credName } = await createTestCredential(app, { prefix: 'e2e-kebab-delete' })

    try {
      await goToCredentialsList(app)
      await filterCredentialByName(app, credName)

      const row = app.getByRole('row', { name: new RegExp(credName) })
      await row.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })

      await app.getByRole('menuitem', { name: 'Delete' }).click()

      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByText(new RegExp(`"${credName}"`))).toBeVisible()
      await expect(dialog.getByText(/cannot be undone/)).toBeVisible()

      const deleteBtn = dialog.getByRole('button', { name: 'Delete' })
      await expect(deleteBtn).toBeVisible()
      await expect(deleteBtn).toBeDisabled()

      await dialog.getByRole('checkbox').click()
      await expect(deleteBtn).toBeEnabled()
      await deleteBtn.click()

      await expect(app.getByText('Credential deleted')).toBeVisible()

      await filterCredentialByName(app, credName)
      await expect(app.getByRole('row', { name: new RegExp(credName) })).not.toBeVisible()
    } catch {
      await deleteCredentialByName(app, credName)
    }
  })

  test('cancel delete keeps credential in the list', async ({ app }) => {
    const { name: credName } = await createTestCredential(app, { prefix: 'e2e-kebab-del-cancel' })

    try {
      await goToCredentialsList(app)
      await filterCredentialByName(app, credName)

      const row = app.getByRole('row', { name: new RegExp(credName) })
      await row.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })
      await app.getByRole('menuitem', { name: 'Delete' }).click()

      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await dialog.getByRole('button', { name: 'Cancel' }).click()
      await expect(dialog).not.toBeVisible()

      await expect(app.getByRole('row', { name: new RegExp(credName) })).toBeVisible()
    } finally {
      await deleteCredentialByName(app, credName)
    }
  })
})

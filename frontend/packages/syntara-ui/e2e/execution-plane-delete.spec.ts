/**
 * E2E: Delete execution target (list + detail)
 *
 * Covers:
 * - List kebab delete → 202 success toast; target leaves the filtered list
 * - Detail kebab delete → navigate back to Execution Plane list
 * - Default target delete → 409 conflict; target remains
 * - In-use target delete → 409 conflict; target remains
 *
 * Skipped when Execution Plane API is unreachable (compose CI does not start it).
 */
import { test, expect, toAppUrl, type Page } from './fixtures'
import {
  createExecutionTargetViaApi,
  deleteExecutionTargetViaApi,
  isExecutionPlaneListReachable,
} from './helpers/execution-plane'
import { openRowKebab } from './helpers/patternfly'
import { buildUniqueName } from './helpers/workflows'

const LIST_URL = '/execution-plane'
const DEFAULT_TARGET_NAME = 'Prod OpenShift West'
const IN_USE_TARGET_NAME = 'Worker Pool 01'

async function filterTargetsByName(app: Page, name: string): Promise<void> {
  await app.getByPlaceholder('Filter by name').fill(name)
  await app.getByRole('button', { name: 'Apply filter' }).click()
}

async function confirmDeleteDialog(app: Page): Promise<void> {
  const dialog = app.getByRole('dialog')
  await expect(dialog.getByText('Delete execution target?')).toBeVisible()
  await dialog.getByRole('checkbox', { name: /permanently deleted/i }).click()
  await dialog.getByRole('button', { name: 'Delete' }).click()
}

test.describe('Execution Plane — delete execution target', { tag: '@pr-check' }, () => {
  test.beforeEach(async ({ app }) => {
    test.skip(
      !(await isExecutionPlaneListReachable(app)),
      'Execution Plane API is not available in this environment (compose CI does not start execution-plane-api)'
    )
  })

  test('deletes from the list and treats 202 as success', async ({ app }) => {
    const name = buildUniqueName('e2e-et-del')
    const created = await createExecutionTargetViaApi(app, { name })
    expect(created, 'Failed to create execution target via API').toBeTruthy()
    const targetId = created!.id

    try {
      await app.goto(toAppUrl(LIST_URL))
      await expect(app.getByRole('heading', { level: 1, name: 'Execution Plane' })).toBeVisible()
      await filterTargetsByName(app, name)

      const row = app.getByRole('row', { name: new RegExp(name) })
      await expect(row).toBeVisible({ timeout: 15_000 })
      await openRowKebab(row, /Delete execution target/i)
      await app.getByRole('menuitem', { name: /Delete execution target/i }).click()
      await confirmDeleteDialog(app)

      await expect(app.getByText('Deletion accepted')).toBeVisible()
      await expect(app.getByRole('row', { name: new RegExp(name) })).toHaveCount(0)
    } finally {
      await deleteExecutionTargetViaApi(app, targetId)
    }
  })

  test('deletes from the detail page and navigates to the list', async ({ app }) => {
    const name = buildUniqueName('e2e-et-del-detail')
    const created = await createExecutionTargetViaApi(app, { name })
    expect(created, 'Failed to create execution target via API').toBeTruthy()
    const targetId = created!.id

    try {
      await app.goto(toAppUrl(`/execution-plane/${targetId}`))
      await expect(app.getByRole('heading', { level: 1, name })).toBeVisible()

      await app.getByRole('button', { name: `Actions for ${name}` }).click()
      await app.getByRole('menuitem', { name: /Delete execution target/i }).click()
      await confirmDeleteDialog(app)

      await expect(app.getByText('Deletion accepted')).toBeVisible()
      await expect(app.getByRole('heading', { level: 1, name: 'Execution Plane' })).toBeVisible()
      await expect(app).toHaveURL(new RegExp(`${LIST_URL}/?$`))
    } finally {
      await deleteExecutionTargetViaApi(app, targetId)
    }
  })

  test('shows conflict when deleting the default target', async ({ app }) => {
    await app.goto(toAppUrl(LIST_URL))
    await expect(app.getByRole('heading', { level: 1, name: 'Execution Plane' })).toBeVisible()
    await filterTargetsByName(app, DEFAULT_TARGET_NAME)

    const row = app.getByRole('row', { name: new RegExp(DEFAULT_TARGET_NAME) })
    await expect(row).toBeVisible({ timeout: 15_000 })
    await openRowKebab(row, /Delete execution target/i)
    await app.getByRole('menuitem', { name: /Delete execution target/i }).click()
    await confirmDeleteDialog(app)

    await expect(app.getByText('Delete failed')).toBeVisible()
    await expect(app.getByText(/promote another target first/i)).toBeVisible()
    await expect(app.getByRole('row', { name: new RegExp(DEFAULT_TARGET_NAME) })).toBeVisible()
  })

  test('shows conflict when deleting an in-use target', async ({ app }) => {
    await app.goto(toAppUrl(LIST_URL))
    await expect(app.getByRole('heading', { level: 1, name: 'Execution Plane' })).toBeVisible()
    await filterTargetsByName(app, IN_USE_TARGET_NAME)

    const row = app.getByRole('row', { name: new RegExp(IN_USE_TARGET_NAME) })
    await expect(row).toBeVisible({ timeout: 15_000 })
    await openRowKebab(row, /Delete execution target/i)
    await app.getByRole('menuitem', { name: /Delete execution target/i }).click()
    await confirmDeleteDialog(app)

    await expect(app.getByText('Delete failed')).toBeVisible()
    await expect(app.getByText(/in use and cannot be deleted/i)).toBeVisible()
    await expect(app.getByRole('row', { name: new RegExp(IN_USE_TARGET_NAME) })).toBeVisible()
  })
})

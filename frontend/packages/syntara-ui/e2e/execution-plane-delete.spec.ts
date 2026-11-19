/**
 * E2E: Delete execution target (list + detail)
 *
 * Covers:
 * - List kebab delete → 202 success toast (target may remain listed while draining)
 * - Detail kebab delete → navigate back to Execution Plane list
 * - Default-target conflict toast (intercepted 409; no mock seed dependency)
 * - In-use conflict toast (intercepted 409; no mock seed dependency)
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

async function withDeleteConflict(
  app: Page,
  targetId: string,
  detail: string,
  run: () => Promise<void>
): Promise<void> {
  const deleteRoute = `**/api/execution_plane/v1/execution_targets/${targetId}`
  await app.route(deleteRoute, async (route) => {
    if (route.request().method() !== 'DELETE') {
      await route.continue()
      return
    }
    await route.fulfill({
      status: 409,
      contentType: 'application/json',
      body: JSON.stringify({
        type: 'https://api.example.com/errors/conflict',
        title: 'Conflict',
        detail,
        code: 'CONFLICT',
        retryable: false,
      }),
    })
  })

  try {
    await run()
  } finally {
    await app.unroute(deleteRoute)
  }
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
    const targetId = created.id

    try {
      await app.goto(toAppUrl(LIST_URL))
      await expect(app.getByRole('heading', { level: 1, name: 'Execution Plane' })).toBeVisible()
      await filterTargetsByName(app, name)

      const row = app.getByRole('row', { name: new RegExp(name) })
      await expect(row).toBeVisible({ timeout: 15_000 })
      await openRowKebab(row, /Delete execution target/i)
      await app.getByRole('menuitem', { name: /Delete execution target/i }).click()
      await confirmDeleteDialog(app)

      // DELETE returns 202 Accepted; the target may remain listed briefly while draining.
      await expect(app.getByText('Deletion accepted')).toBeVisible()
      await expect(app.getByText(/may remain listed briefly while draining completes/i)).toBeVisible()
    } finally {
      await deleteExecutionTargetViaApi(app, targetId)
    }
  })

  test('deletes from the detail page and navigates to the list', async ({ app }) => {
    const name = buildUniqueName('e2e-et-del-detail')
    const created = await createExecutionTargetViaApi(app, { name })
    const targetId = created.id

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
    const name = buildUniqueName('e2e-et-del-default')
    const created = await createExecutionTargetViaApi(app, { name })
    const targetId = created.id
    const conflictDetail = 'Cannot delete the default execution target; promote another target first'

    try {
      await withDeleteConflict(app, targetId, conflictDetail, async () => {
        await app.goto(toAppUrl(LIST_URL))
        await expect(app.getByRole('heading', { level: 1, name: 'Execution Plane' })).toBeVisible()
        await filterTargetsByName(app, name)

        const row = app.getByRole('row', { name: new RegExp(name) })
        await expect(row).toBeVisible({ timeout: 15_000 })
        await openRowKebab(row, /Delete execution target/i)
        await app.getByRole('menuitem', { name: /Delete execution target/i }).click()
        await confirmDeleteDialog(app)

        await expect(app.getByText('Delete failed')).toBeVisible()
        await expect(app.getByText(/promote another target first/i)).toBeVisible()
        await expect(app.getByRole('row', { name: new RegExp(name) })).toBeVisible()
      })
    } finally {
      await deleteExecutionTargetViaApi(app, targetId)
    }
  })

  test('shows conflict when deleting an in-use target', async ({ app }) => {
    const name = buildUniqueName('e2e-et-del-inuse')
    const created = await createExecutionTargetViaApi(app, { name })
    const targetId = created.id
    const conflictDetail = 'Execution target is in use and cannot be deleted'

    try {
      await withDeleteConflict(app, targetId, conflictDetail, async () => {
        await app.goto(toAppUrl(LIST_URL))
        await expect(app.getByRole('heading', { level: 1, name: 'Execution Plane' })).toBeVisible()
        await filterTargetsByName(app, name)

        const row = app.getByRole('row', { name: new RegExp(name) })
        await expect(row).toBeVisible({ timeout: 15_000 })
        await openRowKebab(row, /Delete execution target/i)
        await app.getByRole('menuitem', { name: /Delete execution target/i }).click()
        await confirmDeleteDialog(app)

        await expect(app.getByText('Delete failed')).toBeVisible()
        await expect(app.getByText(/in use and cannot be deleted/i)).toBeVisible()
        await expect(app.getByRole('row', { name: new RegExp(name) })).toBeVisible()
      })
    } finally {
      await deleteExecutionTargetViaApi(app, targetId)
    }
  })
})

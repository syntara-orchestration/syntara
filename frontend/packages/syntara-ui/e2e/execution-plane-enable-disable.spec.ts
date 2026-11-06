/**
 * E2E: Enable / disable execution targets (list + detail)
 *
 * Covers:
 * - List Switch: disable requires confirmation, then PATCH enabled=false
 * - List Switch: enable patches immediately without a dialog
 * - Detail Switch: same disable/enable behavior in the page toolbar
 *
 * Skipped when Execution Plane API is unreachable (compose CI does not start it).
 */
import { test, expect, toAppUrl, type Page } from './fixtures'
import {
  confirmDisableExecutionTarget,
  createExecutionTargetViaApi,
  deleteExecutionTargetViaApi,
  EXECUTION_TARGET_PATCH_TIMEOUT,
  isExecutionPlaneListReachable,
  isExecutionTargetPatchResponse,
  patchExecutionTargetEnabledViaApi,
} from './helpers/execution-plane'
import { buildUniqueName } from './helpers/workflows'

const LIST_URL = '/execution-plane'

async function filterTargetsByName(app: Page, name: string): Promise<void> {
  await app.getByPlaceholder('Filter by name').fill(name)
  await app.getByRole('button', { name: 'Apply filter' }).click()
}

test.describe('Execution Plane — enable/disable execution target', { tag: '@pr-check' }, () => {
  test.beforeEach(async ({ app }) => {
    test.skip(
      !(await isExecutionPlaneListReachable(app)),
      'Execution Plane API is not available in this environment (compose CI does not start execution-plane-api)'
    )
  })

  test('disables from the list after confirmation', async ({ app }) => {
    const name = buildUniqueName('e2e-et-disable')
    const created = await createExecutionTargetViaApi(app, { name })
    const targetId = created.id

    try {
      await app.goto(toAppUrl(LIST_URL))
      await expect(app.getByRole('heading', { level: 1, name: 'Execution Plane' })).toBeVisible()
      await filterTargetsByName(app, name)

      const row = app.getByRole('row', { name: new RegExp(name) })
      await expect(row).toBeVisible({ timeout: 15_000 })
      const toggle = row.getByRole('switch', { name: `Toggle ${name}` })
      await expect(toggle).toBeChecked()

      await toggle.click({ force: true })
      await confirmDisableExecutionTarget(app)

      await expect(toggle).not.toBeChecked()
    } finally {
      await deleteExecutionTargetViaApi(app, targetId)
    }
  })

  test('enables from the list without confirmation', async ({ app }) => {
    const name = buildUniqueName('e2e-et-enable')
    const created = await createExecutionTargetViaApi(app, { name })
    const targetId = created.id

    try {
      await patchExecutionTargetEnabledViaApi(app, targetId, false)

      await app.goto(toAppUrl(LIST_URL))
      await expect(app.getByRole('heading', { level: 1, name: 'Execution Plane' })).toBeVisible()
      await filterTargetsByName(app, name)

      const row = app.getByRole('row', { name: new RegExp(name) })
      await expect(row).toBeVisible({ timeout: 15_000 })
      const toggle = row.getByRole('switch', { name: `Toggle ${name}` })
      await expect(toggle).not.toBeChecked()

      const patchDone = app.waitForResponse(isExecutionTargetPatchResponse, {
        timeout: EXECUTION_TARGET_PATCH_TIMEOUT,
      })
      await toggle.click({ force: true })

      const response = await patchDone
      expect(response.ok(), `PATCH execution target returned ${String(response.status())}`).toBe(true)
      await expect(app.getByRole('dialog')).toHaveCount(0)
      await expect(toggle).toBeChecked()
    } finally {
      await deleteExecutionTargetViaApi(app, targetId)
    }
  })

  test('disables from the detail page after confirmation', async ({ app }) => {
    const name = buildUniqueName('e2e-et-disable-detail')
    const created = await createExecutionTargetViaApi(app, { name })
    const targetId = created.id

    try {
      await app.goto(toAppUrl(`/execution-plane/${targetId}`))
      await expect(app.getByRole('heading', { level: 1, name })).toBeVisible()

      const toggle = app.getByRole('switch', { name: `Toggle ${name}` })
      await expect(toggle).toBeChecked()

      await toggle.click({ force: true })
      await confirmDisableExecutionTarget(app)

      await expect(toggle).not.toBeChecked()
    } finally {
      await deleteExecutionTargetViaApi(app, targetId)
    }
  })

  test('enables from the detail page without confirmation', async ({ app }) => {
    const name = buildUniqueName('e2e-et-enable-detail')
    const created = await createExecutionTargetViaApi(app, { name })
    const targetId = created.id

    try {
      await patchExecutionTargetEnabledViaApi(app, targetId, false)

      await app.goto(toAppUrl(`/execution-plane/${targetId}`))
      await expect(app.getByRole('heading', { level: 1, name })).toBeVisible()

      const toggle = app.getByRole('switch', { name: `Toggle ${name}` })
      await expect(toggle).not.toBeChecked()

      const patchDone = app.waitForResponse(isExecutionTargetPatchResponse, {
        timeout: EXECUTION_TARGET_PATCH_TIMEOUT,
      })
      await toggle.click({ force: true })

      const response = await patchDone
      expect(response.ok(), `PATCH execution target returned ${String(response.status())}`).toBe(true)
      await expect(app.getByRole('dialog')).toHaveCount(0)
      await expect(toggle).toBeChecked()
    } finally {
      await deleteExecutionTargetViaApi(app, targetId)
    }
  })
})

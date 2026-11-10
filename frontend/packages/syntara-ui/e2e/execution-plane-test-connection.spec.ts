/**
 * E2E: Test connection for execution targets (list + detail)
 *
 * Covers:
 * - List kebab → success toast
 * - Detail kebab → success toast
 * - Seeded unhealthy target → failure reason toast
 * - Slow health request → pending (aria-disabled) until settled
 *
 * Skipped when Execution Plane API is unreachable (compose CI does not start it).
 */
import { type Response } from '@playwright/test'

import { test, expect, toAppUrl, type Page } from './fixtures'
import {
  createExecutionTargetViaApi,
  deleteExecutionTargetViaApi,
  isExecutionPlaneListReachable,
} from './helpers/execution-plane'
import { openRowKebab } from './helpers/patternfly'
import { buildUniqueName } from './helpers/workflows'

const LIST_URL = '/execution-plane'
const HEALTH_FAILURE_TARGET_NAME = 'Worker Pool 03'
const HEALTH_TIMEOUT = 20_000

function isExecutionTargetHealthResponse(response: Response): boolean {
  return (
    response.request().method() === 'GET' &&
    /\/api\/execution_plane\/v1\/execution_targets\/[^/]+\/health$/.test(new URL(response.url()).pathname)
  )
}

async function filterTargetsByName(app: Page, name: string): Promise<void> {
  await app.getByPlaceholder('Filter by name').fill(name)
  await app.getByRole('button', { name: 'Apply filter' }).click()
}

test.describe('Execution Plane — test connection', { tag: '@pr-check' }, () => {
  test.beforeEach(async ({ app }) => {
    test.skip(
      !(await isExecutionPlaneListReachable(app)),
      'Execution Plane API is not available in this environment (compose CI does not start execution-plane-api)'
    )
  })

  test('tests connection from the list and shows a success toast', async ({ app }) => {
    const name = buildUniqueName('e2e-et-health')
    const created = await createExecutionTargetViaApi(app, { name })
    const targetId = created.id

    try {
      await app.goto(toAppUrl(LIST_URL))
      await expect(app.getByRole('heading', { level: 1, name: 'Execution Plane' })).toBeVisible()
      await filterTargetsByName(app, name)

      const row = app.getByRole('row', { name: new RegExp(name) })
      await expect(row).toBeVisible({ timeout: 15_000 })

      const healthDone = app.waitForResponse(isExecutionTargetHealthResponse, { timeout: HEALTH_TIMEOUT })
      await openRowKebab(row, /Test connection/i)
      await app.getByRole('menuitem', { name: /Test connection/i }).click()

      const response = await healthDone
      expect(response.ok(), `GET health returned ${String(response.status())}`).toBe(true)

      await expect(app.getByText('Connection successful')).toBeVisible()
      await expect(app.getByText(`Successfully connected to execution target "${name}".`)).toBeVisible()
    } finally {
      await deleteExecutionTargetViaApi(app, targetId)
    }
  })

  test('tests connection from the detail page and shows a success toast', async ({ app }) => {
    const name = buildUniqueName('e2e-et-health-detail')
    const created = await createExecutionTargetViaApi(app, { name })
    const targetId = created.id

    try {
      await app.goto(toAppUrl(`/execution-plane/${targetId}`))
      await expect(app.getByRole('heading', { level: 1, name })).toBeVisible()

      const healthDone = app.waitForResponse(isExecutionTargetHealthResponse, { timeout: HEALTH_TIMEOUT })
      await app.getByRole('button', { name: `Actions for ${name}` }).click()
      await app.getByRole('menuitem', { name: /Test connection/i }).click()

      const response = await healthDone
      expect(response.ok(), `GET health returned ${String(response.status())}`).toBe(true)

      await expect(app.getByText('Connection successful')).toBeVisible()
      await expect(app.getByText(`Successfully connected to execution target "${name}".`)).toBeVisible()
    } finally {
      await deleteExecutionTargetViaApi(app, targetId)
    }
  })

  test('shows the failure reason when the health request is unhealthy', async ({ app }) => {
    await app.goto(toAppUrl(LIST_URL))
    await expect(app.getByRole('heading', { level: 1, name: 'Execution Plane' })).toBeVisible()
    await filterTargetsByName(app, HEALTH_FAILURE_TARGET_NAME)

    const row = app.getByRole('row', { name: new RegExp(HEALTH_FAILURE_TARGET_NAME) })
    await expect(row).toBeVisible({ timeout: 15_000 })

    const healthDone = app.waitForResponse(isExecutionTargetHealthResponse, { timeout: HEALTH_TIMEOUT })
    await openRowKebab(row, /Test connection/i)
    await app.getByRole('menuitem', { name: /Test connection/i }).click()

    const response = await healthDone
    expect(response.ok(), `GET health returned ${String(response.status())}`).toBe(true)

    await expect(app.getByText('Connection failed')).toBeVisible()
    await expect(app.getByText(/connection refused/i)).toBeVisible()
  })

  test('disables Test connection while a slow health request is pending', async ({ app }) => {
    const name = buildUniqueName('e2e-et-health-slow')
    const created = await createExecutionTargetViaApi(app, { name })
    const targetId = created.id

    try {
      await app.route(`**/api/execution_plane/v1/execution_targets/${targetId}/health`, async (route) => {
        await new Promise((resolve) => setTimeout(resolve, 1500))
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ healthy: true, message: null, skipped: false }),
        })
      })

      await app.goto(toAppUrl(LIST_URL))
      await expect(app.getByRole('heading', { level: 1, name: 'Execution Plane' })).toBeVisible()
      await filterTargetsByName(app, name)

      const row = app.getByRole('row', { name: new RegExp(name) })
      await expect(row).toBeVisible({ timeout: 15_000 })

      await openRowKebab(row, /Test connection/i)
      await app.getByRole('menuitem', { name: /Test connection/i }).click()

      await openRowKebab(row, /Test connection/i)
      await expect(app.getByRole('menuitem', { name: /Test connection/i })).toHaveAttribute('aria-disabled', 'true')

      await expect(app.getByText('Connection successful')).toBeVisible({ timeout: HEALTH_TIMEOUT })
    } finally {
      await app.unroute(`**/api/execution_plane/v1/execution_targets/${targetId}/health`)
      await deleteExecutionTargetViaApi(app, targetId)
    }
  })
})

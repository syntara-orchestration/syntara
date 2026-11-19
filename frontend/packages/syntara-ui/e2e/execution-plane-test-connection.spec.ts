/**
 * E2E: Test connection for execution targets (list + detail)
 *
 * Covers:
 * - List kebab → success toast (intercepted healthy response)
 * - Detail kebab → success toast (intercepted healthy response)
 * - Intercepted unhealthy health response → failure reason toast
 * - Slow health request → pending (aria-disabled) until settled
 *
 * Health responses are intercepted so CI does not depend on a freshly created
 * target being reachable from the live Execution Plane probe.
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
const HEALTH_TIMEOUT = 20_000

function isExecutionTargetHealthResponse(response: Response): boolean {
  return (
    response.request().method() === 'GET' &&
    /\/api\/execution_plane\/v1\/execution_targets\/[^/]+\/health$/.test(new URL(response.url()).pathname)
  )
}

function healthRouteFor(targetId: string): string {
  return `**/api/execution_plane/v1/execution_targets/${targetId}/health`
}

async function filterTargetsByName(app: Page, name: string): Promise<void> {
  await app.getByPlaceholder('Filter by name').fill(name)
  await app.getByRole('button', { name: 'Apply filter' }).click()
}

async function fulfillHealth(
  app: Page,
  targetId: string,
  body: { healthy: boolean; message: string | null; skipped: boolean },
  options?: { delayMs?: number }
): Promise<string> {
  const route = healthRouteFor(targetId)
  await app.route(route, async (routeHandler) => {
    if (options?.delayMs) {
      await new Promise((resolve) => setTimeout(resolve, options.delayMs))
    }
    await routeHandler.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
  })
  return route
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
    const healthRoute = await fulfillHealth(app, targetId, { healthy: true, message: null, skipped: false })

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
      await app.unroute(healthRoute)
      await deleteExecutionTargetViaApi(app, targetId)
    }
  })

  test('tests connection from the detail page and shows a success toast', async ({ app }) => {
    const name = buildUniqueName('e2e-et-health-detail')
    const created = await createExecutionTargetViaApi(app, { name })
    const targetId = created.id
    const healthRoute = await fulfillHealth(app, targetId, { healthy: true, message: null, skipped: false })

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
      await app.unroute(healthRoute)
      await deleteExecutionTargetViaApi(app, targetId)
    }
  })

  test('shows the failure reason when the health request is unhealthy', async ({ app }) => {
    const name = buildUniqueName('e2e-et-health-fail')
    const created = await createExecutionTargetViaApi(app, { name })
    const targetId = created.id
    const failureMessage = `Unable to reach execution target "${name}": connection refused`
    const healthRoute = await fulfillHealth(app, targetId, {
      healthy: false,
      message: failureMessage,
      skipped: false,
    })

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

      await expect(app.getByText('Connection failed')).toBeVisible()
      await expect(app.getByText(failureMessage)).toBeVisible()
    } finally {
      await app.unroute(healthRoute)
      await deleteExecutionTargetViaApi(app, targetId)
    }
  })

  test('disables Test connection while a slow health request is pending', async ({ app }) => {
    const name = buildUniqueName('e2e-et-health-slow')
    const created = await createExecutionTargetViaApi(app, { name })
    const targetId = created.id
    const healthRoute = await fulfillHealth(
      app,
      targetId,
      { healthy: true, message: null, skipped: false },
      { delayMs: 1500 }
    )

    try {
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
      await app.unroute(healthRoute)
      await deleteExecutionTargetViaApi(app, targetId)
    }
  })
})

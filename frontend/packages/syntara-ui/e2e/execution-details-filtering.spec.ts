/**
 * E2E Tests: Execution Details — Activity Filtering
 *
 * Tests the client-side activity filter bar on the execution details panel.
 * The panel has three filter fields:
 *   - Keyword (text search on activity name)
 *   - Type (select: Script, Condition, Approval, etc.)
 *   - Status (select: Successful, Failed, Waiting for approval, etc.)
 *
 * These filters are local state (not URL-driven) and operate on the
 * activity list rendered in the "Overview" tab of the execution details panel.
 *
 * Setup is fully self-contained: each suite creates a workflow + execution via
 * API. Against the mock API, activities are synthesized from the workflow
 * definition; against a real backend, the Temporal worker produces them.
 * Assertions prefer semantic row visibility over exact total counts because the
 * real backend also surfaces the manual trigger (and possibly other) activities.
 *
 * Status-filter suite: CI's Approvals service is often unreachable from the
 * worker, so approval nodes fail instead of staying `waiting`. Those tests
 * use the documented partial-mock + routeWebSocket patterns from
 * frontend-playwright-e2e so Staging Tests stays completed and the approval
 * gate stays waiting without relying on that external service.
 *
 * Note: Timestamp range filters and WebSocket real-time update tests are
 * not applicable — the activity filter bar has no date range filter, and
 * the mock API does not support WebSocket connections.
 */

import { test, expect, toAppUrl, type Page } from './fixtures'
import { buildUniqueName } from './helpers/workflows'
import { apiRequest, createWorkflowViaApi, deleteWorkflowViaApi, getAuthToken } from './utils/api'

/**
 * Get the activity filter toolbar, scoped to the execution details panel.
 * The page has two `search "Filters"` elements — one for activity filtering
 * and one inside the Run History card. Scope via the activity filter region.
 */
function getActivityFilterToolbar(app: Page) {
  return app.getByRole('region', { name: 'Activity filter' }).getByRole('search', { name: 'Filters' })
}

/** Navigate to an execution detail page and wait for the activity table to load. */
async function navigateToExecution(app: Page, executionId: string): Promise<boolean> {
  await app.goto(toAppUrl(`/executions/${executionId}`))
  const activityTable = app.getByRole('grid', { name: 'Activity states' })
  return activityTable
    .waitFor({ state: 'visible', timeout: 15_000 })
    .then(() => true)
    .catch(() => false)
}

/** Switch the filter field selector to a different field. */
async function switchFieldSelector(app: Page, currentFieldLabel: string, targetField: string): Promise<void> {
  const filterToolbar = getActivityFilterToolbar(app)
  await filterToolbar.getByRole('button', { name: currentFieldLabel, exact: true }).click()
  await app.getByRole('option', { name: targetField }).click()
}

/** Apply a keyword (text) filter by typing into the search input and pressing Enter. */
async function applyKeywordFilter(app: Page, keyword: string): Promise<void> {
  const filterToolbar = getActivityFilterToolbar(app)
  const searchInput = filterToolbar.getByRole('textbox', { name: 'Keyword filter' })
  await searchInput.fill(keyword)
  await searchInput.press('Enter')
}

async function createExecutionViaApi(page: Page, workflowId: string): Promise<string | null> {
  const token = await getAuthToken(page)
  if (!token) return null
  const resp = await apiRequest(page, 'post', '/executions', {
    token,
    data: { workflow_id: workflowId, trigger_node_id: 'trigger_manual' },
  })
  if (!resp.ok()) return null
  const body = (await resp.json()) as { id: string }
  return body.id
}

type ActivityRecord = Record<string, unknown>

function activityKey(activity: ActivityRecord): string {
  const name = activity.activity_name
  if (typeof name === 'string' && name) return name
  const id = activity.activity_id
  if (typeof id === 'string' && id) return id
  return ''
}

/**
 * Stabilize activity statuses for the status-filter suite.
 *
 * Uses the project's documented partial-mock pattern (route.fetch → patch →
 * fulfill) and routeWebSocket (see frontend-playwright-e2e skill). Required
 * because CI's Approvals API is often unreachable from the worker, so the
 * approval node fails instead of staying `waiting`.
 *
 * Must be registered before navigation that loads the execution.
 */
async function installStableApprovalActivityStatuses(app: Page, executionId: string) {
  // Do not connectToServer — drop live patches that would flip waiting → failed.
  await app.routeWebSocket(`**/ws/workflows/v1/executions/${executionId}**`, () => {})

  await app.route(`**/api/v1/executions/${executionId}**`, async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue()
      return
    }

    const url = new URL(route.request().url())
    // Only the execution detail resource — not /cancel, /activities, etc.
    if (!/\/api\/v1\/executions\/[^/]+$/.test(url.pathname)) {
      await route.continue()
      return
    }

    const response = await route.fetch()
    const body = (await response.json()) as {
      activities?: ActivityRecord[]
      status?: string
      approval_pending?: boolean
    }

    const ts = '2024-01-15T10:00:00Z'
    const byName = new Map((body.activities ?? []).map((activity) => [activityKey(activity), activity]))

    const stagingBase: ActivityRecord = byName.get('staging_tests') ?? {
      id: `act-${executionId}-staging`,
      execution_id: executionId,
      activity_name: 'staging_tests',
      node_type: 'script',
      temporal_activity_id: `tmp-${executionId}-staging`,
      input_data: {},
      output_data: {},
      error_details: null,
      retry_count: 0,
      iteration: null,
    }
    const approvalBase: ActivityRecord = byName.get('approval_gate') ?? {
      id: `act-${executionId}-approval`,
      execution_id: executionId,
      activity_name: 'approval_gate',
      node_type: 'approval',
      temporal_activity_id: `tmp-${executionId}-approval`,
      input_data: {},
      output_data: null,
      error_details: null,
      retry_count: 0,
      iteration: null,
    }

    const rewritten: ActivityRecord[] = [
      {
        ...stagingBase,
        status: 'completed',
        started_at: stagingBase.started_at ?? ts,
        completed_at: stagingBase.completed_at ?? ts,
        created_at: stagingBase.created_at ?? ts,
        updated_at: ts,
      },
      {
        ...approvalBase,
        status: 'waiting',
        started_at: approvalBase.started_at ?? ts,
        completed_at: null,
        created_at: approvalBase.created_at ?? ts,
        updated_at: ts,
        error_details: null,
      },
    ]

    for (const [name, activity] of byName) {
      if (name === 'staging_tests' || name === 'approval_gate' || !name) continue
      // Keep extras (e.g. manual trigger) but never leave them as waiting —
      // waiting-filter tests assert a single matching row.
      rewritten.push({
        ...activity,
        status: activity.status === 'waiting' ? 'completed' : activity.status,
      })
    }

    body.activities = rewritten
    body.status = 'paused'
    body.approval_pending = true

    await route.fulfill({ response, json: body })
  })
}

/**
 * Named activity rows only — excludes the header and error-detail rows that
 * PatternFly renders as additional tbody rows without a Name cell.
 */
function activityDataRows(app: Page) {
  return app
    .getByRole('grid', { name: 'Activity states' })
    .locator('tbody')
    .getByRole('row')
    .filter({ has: app.locator('[data-label="Name"]') })
}

test.describe('Execution Details — Activity Filtering', { tag: '@pr-check' }, () => {
  // Workflow with script + condition activities (plus a manual trigger on real backends):
  //   - Check Temperature (script)
  //   - Temperature-Based Routing (condition)
  //   - Hot Weather Action (script)
  test.describe('keyword and type filters', () => {
    let workflowId: string | null = null
    let executionId: string | null = null

    test.beforeAll(async ({ browser }) => {
      const page = await browser.newPage()
      try {
        const workflowName = buildUniqueName('e2e-act-filter')
        ;({ id: workflowId } = await createWorkflowViaApi({
          app: page,
          name: workflowName,
          triggers: [{ id: 'trigger_manual', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
          nodes: [
            {
              id: 'check_temperature',
              type: 'script',
              name: 'Check Temperature',
              parameters: { language: 'python', code: 'print(42)' },
            },
            {
              id: 'temperature_routing',
              type: 'condition',
              name: 'Temperature-Based Routing',
              parameters: { condition: 'true' },
            },
            {
              id: 'hot_weather',
              type: 'script',
              name: 'Hot Weather Action',
              parameters: { language: 'python', code: 'print("hot")' },
            },
          ],
          edges: [
            { from: 'trigger_manual', to: 'check_temperature' },
            { from: 'check_temperature', to: 'temperature_routing' },
            { from: 'temperature_routing', to: 'hot_weather', from_port: 'true' },
          ],
        }))
        executionId = await createExecutionViaApi(page, workflowId)
      } finally {
        await page.close()
      }
    })

    test.afterAll(async ({ browser }) => {
      if (!workflowId) return
      const page = await browser.newPage()
      try {
        await deleteWorkflowViaApi(page, workflowId)
      } finally {
        await page.close()
      }
    })

    test.beforeEach(async ({ app }) => {
      expect(executionId, 'Failed to create workflow/execution for activity filter tests').toBeTruthy()
      const hasData = await navigateToExecution(app, executionId!)
      expect(hasData, 'Execution activities not available').toBeTruthy()
      // Real backend needs the worker to finish before filter targets exist.
      const ready = await app
        .getByRole('row', { name: /Hot Weather Action/ })
        .waitFor({ state: 'visible', timeout: 30_000 })
        .then(() => true)
        .catch(() => false)
      expect(ready, 'Workflow activities not ready — Temporal worker may not be running').toBeTruthy()
    })

    test('keyword search filters activities by name substring', async ({ app }) => {
      const filterToolbar = getActivityFilterToolbar(app)
      const rows = activityDataRows(app)

      await expect(app.getByRole('row', { name: /Check Temperature/ })).toBeVisible()
      await expect(app.getByRole('row', { name: /Temperature-Based Routing/ })).toBeVisible()
      await expect(app.getByRole('row', { name: /Hot Weather Action/ })).toBeVisible()

      await applyKeywordFilter(app, 'Temperature')

      // "Temperature" matches "Check Temperature" and "Temperature-Based Routing"
      await expect(app.getByRole('row', { name: /Check Temperature/ })).toBeVisible()
      await expect(app.getByRole('row', { name: /Temperature-Based Routing/ })).toBeVisible()
      await expect(app.getByRole('row', { name: /Hot Weather Action/ })).not.toBeVisible()
      await expect(rows).toHaveCount(2)

      const keywordChipGroup = filterToolbar.getByRole('list', { name: 'Keyword' })
      await expect(keywordChipGroup).toBeVisible()
      await expect(keywordChipGroup.getByText('Temperature')).toBeVisible()
    })

    test('type filter narrows activities by node type', async ({ app }) => {
      const filterToolbar = getActivityFilterToolbar(app)
      const rows = activityDataRows(app)

      await switchFieldSelector(app, 'Keyword', 'Type')
      await filterToolbar.getByRole('button', { name: 'Filter by type' }).click()
      await app.getByRole('option', { name: 'Condition' }).click()

      await expect(app.getByRole('row', { name: /Temperature-Based Routing/ })).toBeVisible()
      await expect(app.getByRole('row', { name: /Check Temperature/ })).not.toBeVisible()
      await expect(app.getByRole('row', { name: /Hot Weather Action/ })).not.toBeVisible()
      await expect(rows).toHaveCount(1)

      const typeChipGroup = filterToolbar.getByRole('list', { name: 'Type' })
      await expect(typeChipGroup).toBeVisible()
      await expect(typeChipGroup.getByText('Condition')).toBeVisible()
    })

    test('combined keyword + type filters narrow results further', async ({ app }) => {
      const filterToolbar = getActivityFilterToolbar(app)
      const rows = activityDataRows(app)

      await applyKeywordFilter(app, 'Check')
      await expect(app.getByRole('row', { name: /Check Temperature/ })).toBeVisible()
      await expect(rows).toHaveCount(1)

      await switchFieldSelector(app, 'Keyword', 'Type')
      await filterToolbar.getByRole('button', { name: 'Filter by type' }).click()
      await app.getByRole('option', { name: 'Script' }).click()

      await expect(app.getByRole('row', { name: /Check Temperature/ })).toBeVisible()
      await expect(rows).toHaveCount(1)

      const keywordChipGroup = filterToolbar.getByRole('list', { name: 'Keyword' })
      const typeChipGroup = filterToolbar.getByRole('list', { name: 'Type' })
      await expect(keywordChipGroup.getByText('Check')).toBeVisible()
      await expect(typeChipGroup.getByText('Script')).toBeVisible()
    })

    test('empty state when no activities match filter', async ({ app }) => {
      const activityTable = app.getByRole('grid', { name: 'Activity states' })

      // Use a unique keyword — status "Failed" can match real-backend failures.
      await applyKeywordFilter(app, 'zzz-nomatch-activity-filter')

      await expect(activityTable).not.toBeVisible()
      await expect(app.getByRole('heading', { name: 'No results found' })).toBeVisible()

      await app.getByRole('button', { name: 'Clear all filters' }).click()

      await expect(activityTable).toBeVisible()
      await expect(app.getByRole('row', { name: /Check Temperature/ })).toBeVisible()
      await expect(app.getByRole('row', { name: /Temperature-Based Routing/ })).toBeVisible()
      await expect(app.getByRole('row', { name: /Hot Weather Action/ })).toBeVisible()
    })

    test('filter chip removal restores full activity list', async ({ app }) => {
      const filterToolbar = getActivityFilterToolbar(app)
      const rows = activityDataRows(app)

      await applyKeywordFilter(app, 'Hot')
      await expect(app.getByRole('row', { name: /Hot Weather Action/ })).toBeVisible()
      await expect(rows).toHaveCount(1)

      const keywordChipGroup = filterToolbar.getByRole('list', { name: 'Keyword' })
      await keywordChipGroup.getByRole('button', { name: 'Close Hot' }).click()

      await expect(keywordChipGroup).not.toBeVisible()
      await expect(app.getByRole('row', { name: /Check Temperature/ })).toBeVisible()
      await expect(app.getByRole('row', { name: /Temperature-Based Routing/ })).toBeVisible()
      await expect(app.getByRole('row', { name: /Hot Weather Action/ })).toBeVisible()
    })
  })

  // Workflow with a completed script + an approval gate:
  //   - Staging Tests (script, completed)
  //   - Production Deployment Approval (approval, waiting once the worker pauses)
  test.describe('status filter', () => {
    let workflowId: string | null = null
    let executionId: string | null = null

    test.beforeAll(async ({ browser }) => {
      const page = await browser.newPage()
      try {
        const workflowName = buildUniqueName('e2e-act-status')
        ;({ id: workflowId } = await createWorkflowViaApi({
          app: page,
          name: workflowName,
          triggers: [{ id: 'trigger_manual', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
          nodes: [
            {
              id: 'staging_tests',
              type: 'script',
              name: 'Staging Tests',
              parameters: { language: 'python', code: 'print("ok")' },
            },
            {
              id: 'approval_gate',
              type: 'approval',
              name: 'Production Deployment Approval',
              parameters: { approvers: [], message: 'Approve deployment' },
            },
          ],
          edges: [
            { from: 'trigger_manual', to: 'staging_tests' },
            { from: 'staging_tests', to: 'approval_gate' },
          ],
        }))
        executionId = await createExecutionViaApi(page, workflowId)
      } finally {
        await page.close()
      }
    })

    test.afterAll(async ({ browser }) => {
      if (!workflowId) return
      const page = await browser.newPage()
      try {
        await deleteWorkflowViaApi(page, workflowId)
      } finally {
        await page.close()
      }
    })

    test.beforeEach(async ({ app }) => {
      expect(executionId, 'Failed to create workflow/execution for status filter tests').toBeTruthy()
      await installStableApprovalActivityStatuses(app, executionId!)
      const hasData = await navigateToExecution(app, executionId!)
      expect(hasData, 'Execution activities not available').toBeTruthy()
      const approvalReady = await app
        .getByRole('row', { name: /Production Deployment Approval/ })
        .waitFor({ state: 'visible', timeout: 30_000 })
        .then(() => true)
        .catch(() => false)
      expect(approvalReady, 'Approval activity not available').toBeTruthy()
      await expect(
        app.getByRole('row', { name: /Production Deployment Approval/ }).getByText('Waiting for approval')
      ).toBeVisible({ timeout: 10_000 })
    })

    test('status filter: Successful shows only matching activities', async ({ app }) => {
      const filterToolbar = getActivityFilterToolbar(app)

      await switchFieldSelector(app, 'Keyword', 'Status')
      await filterToolbar.getByRole('button', { name: 'Filter by status' }).click()
      await app.getByRole('option', { name: 'Successful', exact: true }).click()

      await expect(app.getByRole('row', { name: /Staging Tests/ })).toBeVisible()
      await expect(app.getByRole('row', { name: /Production Deployment Approval/ })).not.toBeVisible()
      await expect(filterToolbar.getByRole('list', { name: 'Status' }).getByText('Successful')).toBeVisible()
    })

    test('status filter: Waiting for approval shows only matching activities', async ({ app }) => {
      const filterToolbar = getActivityFilterToolbar(app)
      const rows = activityDataRows(app)

      await switchFieldSelector(app, 'Keyword', 'Status')
      await filterToolbar.getByRole('button', { name: 'Filter by status' }).click()
      await app.getByRole('option', { name: 'Waiting for approval' }).click()

      await expect(app.getByRole('row', { name: /Production Deployment Approval/ })).toBeVisible()
      await expect(app.getByRole('row', { name: /Staging Tests/ })).not.toBeVisible()
      await expect(rows).toHaveCount(1)
      await expect(filterToolbar.getByRole('list', { name: 'Status' }).getByText('Waiting for approval')).toBeVisible()
    })

    test('selecting a new status option replaces the previous chip', async ({ app }) => {
      const filterToolbar = getActivityFilterToolbar(app)
      const statusChipGroup = filterToolbar.getByRole('list', { name: 'Status' })

      await switchFieldSelector(app, 'Keyword', 'Status')
      await filterToolbar.getByRole('button', { name: 'Filter by status' }).click()
      await app.getByRole('option', { name: 'Successful', exact: true }).click()

      await expect(statusChipGroup.getByText('Successful')).toBeVisible()
      await expect(app.getByRole('row', { name: /Staging Tests/ })).toBeVisible()

      await filterToolbar.getByRole('button', { name: 'Successful', exact: true }).click()
      await app.getByRole('option', { name: 'Waiting for approval' }).click()

      await expect(statusChipGroup.getByText('Waiting for approval')).toBeVisible()
      await expect(statusChipGroup.getByText('Successful')).not.toBeVisible()
      await expect(app.getByRole('row', { name: /Production Deployment Approval/ })).toBeVisible()
      await expect(app.getByRole('row', { name: /Staging Tests/ })).not.toBeVisible()
    })

    test('removing one filter from combined filters keeps the other active', async ({ app }) => {
      const filterToolbar = getActivityFilterToolbar(app)
      const rows = activityDataRows(app)

      await applyKeywordFilter(app, 'Staging')
      await expect(app.getByRole('row', { name: /Staging Tests/ })).toBeVisible()
      await expect(rows).toHaveCount(1)

      await switchFieldSelector(app, 'Keyword', 'Status')
      await filterToolbar.getByRole('button', { name: 'Filter by status' }).click()
      await app.getByRole('option', { name: 'Successful', exact: true }).click()

      await expect(app.getByRole('row', { name: /Staging Tests/ })).toBeVisible()
      await expect(rows).toHaveCount(1)

      const keywordChipGroup = filterToolbar.getByRole('list', { name: 'Keyword' })
      const statusChipGroup = filterToolbar.getByRole('list', { name: 'Status' })
      await expect(keywordChipGroup.getByText('Staging')).toBeVisible()
      await expect(statusChipGroup.getByText('Successful')).toBeVisible()

      await keywordChipGroup.getByRole('button', { name: 'Close Staging' }).click()

      await expect(keywordChipGroup).not.toBeVisible()
      await expect(statusChipGroup.getByText('Successful')).toBeVisible()
      await expect(app.getByRole('row', { name: /Staging Tests/ })).toBeVisible()
      await expect(app.getByRole('row', { name: /Production Deployment Approval/ })).not.toBeVisible()
    })
  })
})

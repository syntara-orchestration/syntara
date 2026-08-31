/**
 * E2E tests: Run history panel filtering
 *
 * Critical paths covered:
 * - Status filter apply / remove / switch
 * - Version filter
 * - Combined status + version filters
 * - Empty state with clear-all
 * - Chip removal
 * - Panel open/close
 * - Execution row metadata display
 *
 * Setup:
 * - Creates a real workflow via API (builder needs a valid workflow id)
 * - Intercepts GET /executions for that workflow with mixed-status fixtures so
 *   filters work the same against mock API and the real backend CI cluster
 *   (POST /executions cannot seed terminal statuses on the real API)
 * - Cleans up the workflow in afterAll
 */

import { test, expect, toAppUrl, type Page } from './fixtures'
import { buildUniqueName, waitForUIReady } from './helpers/workflows'
import { createWorkflowViaApi, deleteWorkflowViaApi } from './seeds/resources'
import { getAuthToken } from './utils/api'

const COMPLETED_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const FAILED_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
const RUNNING_ID = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
const CANCELLED_ID = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd'
const VERSION_ID = 'wv-e2e-rh-filter-1'
const VERSION_LABEL = 'v1'

type SeededExecution = {
  id: string
  status: string
  workflow_id: string
  workflow_version: number
  workflow_version_id: string
  workflow_version_name: string
  workflow_version_created_at: string
  created_at: string
  updated_at: string
  started_at: string
  completed_at: string | null
  started_by: string
  input_data: Record<string, never>
}

function truncatedRunId(executionId: string): string {
  return executionId.slice(0, 8)
}

function buildSeededExecutions(workflowId: string): SeededExecution[] {
  const shared = {
    workflow_id: workflowId,
    workflow_version: 1,
    workflow_version_id: VERSION_ID,
    workflow_version_name: VERSION_LABEL,
    workflow_version_created_at: '2024-01-15T09:00:00Z',
    started_by: 'user-1',
    input_data: {},
  } as const

  return [
    {
      ...shared,
      id: COMPLETED_ID,
      status: 'completed',
      created_at: '2024-01-15T10:00:00Z',
      updated_at: '2024-01-15T10:05:00Z',
      started_at: '2024-01-15T10:00:00Z',
      completed_at: '2024-01-15T10:05:00Z',
    },
    {
      ...shared,
      id: FAILED_ID,
      status: 'failed',
      created_at: '2024-01-15T11:00:00Z',
      updated_at: '2024-01-15T11:02:00Z',
      started_at: '2024-01-15T11:00:00Z',
      completed_at: '2024-01-15T11:02:00Z',
    },
    {
      ...shared,
      id: RUNNING_ID,
      status: 'running',
      created_at: '2024-01-15T12:00:00Z',
      updated_at: '2024-01-15T12:00:00Z',
      started_at: '2024-01-15T12:00:00Z',
      completed_at: null,
    },
    {
      ...shared,
      id: CANCELLED_ID,
      status: 'cancelled',
      created_at: '2024-01-15T13:00:00Z',
      updated_at: '2024-01-15T13:01:00Z',
      started_at: '2024-01-15T13:00:00Z',
      completed_at: '2024-01-15T13:01:00Z',
    },
  ]
}

/**
 * Intercept list GET /executions for this workflow and honor status /
 * workflow_version_id query params. Detail routes (/executions/:id) continue.
 */
async function installExecutionsListRoute(app: Page, workflowId: string) {
  const seeded = buildSeededExecutions(workflowId)

  await app.route('**/api/v1/executions**', async (route) => {
    const request = route.request()
    if (request.method() !== 'GET') {
      await route.continue()
      return
    }

    const url = new URL(request.url())
    if (/\/api\/v1\/executions\/[^/?]+/.test(url.pathname)) {
      await route.continue()
      return
    }
    if (url.searchParams.get('workflow_id') !== workflowId) {
      await route.continue()
      return
    }

    let filtered = seeded
    const status = url.searchParams.get('status')
    if (status) {
      filtered = filtered.filter((execution) => execution.status === status)
    }
    if (url.searchParams.get('approval_pending') === 'true') {
      filtered = filtered.filter((execution) => (execution as { approval_pending?: boolean }).approval_pending === true)
    }
    const versionId = url.searchParams.get('workflow_version_id')
    if (versionId) {
      filtered = filtered.filter((execution) => execution.workflow_version_id === versionId)
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      json: {
        resources: filtered,
        next: null,
        prev: null,
        total: filtered.length,
      },
    })
  })
}

async function openRunHistoryPanel(app: Page, workflowId: string, expectedRunIdPrefix: string) {
  await installExecutionsListRoute(app, workflowId)
  await app.goto(toAppUrl(`/workflow-builder/${workflowId}`))
  await waitForUIReady(app)

  const kebab = app.getByRole('button', { name: 'Workflow actions' })
  await expect(kebab).toBeVisible({ timeout: 10_000 })
  await kebab.click()

  const runHistoryItem = app.getByRole('menuitem', { name: 'Run history' })
  await expect(runHistoryItem).toBeVisible()
  await runHistoryItem.click()

  await expect(app.getByRole('heading', { name: 'Run history', level: 2 })).toBeVisible()
  await expect(app.getByText(`Run ID: ${expectedRunIdPrefix}`)).toBeVisible({ timeout: 10_000 })
}

function filterToolbar(app: Page) {
  return app.getByRole('search', { name: 'Filters' })
}

async function applyVersionFilter(app: Page): Promise<string> {
  const versionToggle = filterToolbar(app).getByRole('button', { name: 'Filter by version' })
  await expect(versionToggle).toBeVisible()
  await versionToggle.click()

  // Scope to the open listbox so we don't match options from other selects
  const versionListbox = app.getByRole('listbox')
  const versionOption = versionListbox.getByRole('option')
  await expect(versionOption).toHaveCount(1)
  const optionText = (await versionOption.textContent())?.trim()
  if (!optionText) throw new Error('Version filter option had no text')
  await versionOption.click()
  return optionText
}

let workflowId: string | null = null

test.describe('Run history panel filtering', { tag: '@pr-check' }, () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    try {
      const token = await getAuthToken(page)
      if (!token) throw new Error('Could not obtain auth token')

      const workflow = await createWorkflowViaApi(page, {
        name: buildUniqueName('e2e-rh-filter'),
        token,
      })
      if (!workflow) throw new Error('Could not create test workflow')
      workflowId = workflow.id
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

  test.beforeEach(() => {
    expect(workflowId, 'Failed to create workflow for run history tests').toBeTruthy()
  })

  test('status filter: apply and verify filtered results', async ({ app }) => {
    await openRunHistoryPanel(app, workflowId!, truncatedRunId(COMPLETED_ID))

    await filterToolbar(app).getByRole('button', { name: 'Filter by status' }).click()
    await app.getByRole('option', { name: 'Failed' }).click()

    const statusChipGroup = filterToolbar(app).getByRole('list', { name: 'Status' })
    await expect(statusChipGroup.getByText('Failed')).toBeVisible()

    await expect(app.getByText(`Run ID: ${truncatedRunId(FAILED_ID)}`)).toBeVisible()
    await expect(app.getByText(`Run ID: ${truncatedRunId(COMPLETED_ID)}`)).not.toBeVisible()

    await statusChipGroup.getByRole('button', { name: 'Close Failed' }).click()

    await expect(statusChipGroup).not.toBeVisible()
    await expect(app.getByText(`Run ID: ${truncatedRunId(COMPLETED_ID)}`)).toBeVisible()
  })

  test('status filter: switch between status values', async ({ app }) => {
    await openRunHistoryPanel(app, workflowId!, truncatedRunId(COMPLETED_ID))

    await filterToolbar(app).getByRole('button', { name: 'Filter by status' }).click()
    await app.getByRole('option', { name: 'Completed', exact: true }).click()

    const statusChipGroup = filterToolbar(app).getByRole('list', { name: 'Status' })
    await expect(statusChipGroup.getByText('Completed')).toBeVisible()
    await expect(app.getByText(`Run ID: ${truncatedRunId(COMPLETED_ID)}`)).toBeVisible()

    await filterToolbar(app).getByRole('button', { name: 'Completed', exact: true }).click()
    await app.getByRole('option', { name: 'Running' }).click()

    await expect(statusChipGroup.getByText('Running')).toBeVisible()
    await expect(statusChipGroup.getByText('Completed')).not.toBeVisible()
    await expect(app.getByText(`Run ID: ${truncatedRunId(COMPLETED_ID)}`)).not.toBeVisible()
  })

  test('version filter: switch to version field and apply filter', async ({ app }) => {
    await openRunHistoryPanel(app, workflowId!, truncatedRunId(COMPLETED_ID))

    const fieldSelector = filterToolbar(app).getByRole('button', { name: 'Status', exact: true })
    await fieldSelector.click()
    await app.getByRole('option', { name: 'Version' }).click()

    const optionText = await applyVersionFilter(app)
    expect(optionText).toBe(VERSION_LABEL)

    const versionChipGroup = filterToolbar(app).getByRole('list', { name: 'Version' })
    await expect(versionChipGroup).toBeVisible()
    await expect(versionChipGroup.getByText(optionText)).toBeVisible()

    await versionChipGroup.getByRole('button', { name: `Close ${optionText}` }).click()
    await expect(versionChipGroup).not.toBeVisible()
  })

  test('combined filters: status + version applied together', async ({ app }) => {
    await openRunHistoryPanel(app, workflowId!, truncatedRunId(COMPLETED_ID))

    await filterToolbar(app).getByRole('button', { name: 'Filter by status' }).click()
    await app.getByRole('option', { name: 'Completed', exact: true }).click()

    const statusChipGroup = filterToolbar(app).getByRole('list', { name: 'Status' })
    await expect(statusChipGroup.getByText('Completed')).toBeVisible()

    const fieldSelector = filterToolbar(app).getByRole('button', { name: 'Status', exact: true })
    await fieldSelector.click()
    await app.getByRole('option', { name: 'Version' }).click()

    const optionText = await applyVersionFilter(app)

    await expect(statusChipGroup.getByText('Completed')).toBeVisible()
    const versionChipGroup = filterToolbar(app).getByRole('list', { name: 'Version' })
    await expect(versionChipGroup).toBeVisible()
    await expect(app.getByText(`Run ID: ${truncatedRunId(COMPLETED_ID)}`)).toBeVisible()

    await statusChipGroup.getByRole('button', { name: 'Close Completed' }).click()
    await expect(statusChipGroup).not.toBeVisible()
    await expect(versionChipGroup).toBeVisible()

    await versionChipGroup.getByRole('button', { name: `Close ${optionText}` }).click()
    await expect(versionChipGroup).not.toBeVisible()
  })

  test('empty state shows when filters return no results', async ({ app }) => {
    await openRunHistoryPanel(app, workflowId!, truncatedRunId(COMPLETED_ID))

    await filterToolbar(app).getByRole('button', { name: 'Filter by status' }).click()
    await app.getByRole('option', { name: 'Pending', exact: true }).click()

    await expect(app.getByRole('heading', { name: 'No results found' })).toBeVisible()
    await expect(app.getByText('No results match the filter criteria')).toBeVisible()

    await app.getByRole('button', { name: 'Clear all filters' }).click()

    await expect(app.getByText(`Run ID: ${truncatedRunId(COMPLETED_ID)}`)).toBeVisible()
    await expect(app.getByRole('heading', { name: 'No results found' })).not.toBeVisible()
  })

  test('individual filter chips can be removed', async ({ app }) => {
    await openRunHistoryPanel(app, workflowId!, truncatedRunId(COMPLETED_ID))

    await filterToolbar(app).getByRole('button', { name: 'Filter by status' }).click()
    await app.getByRole('option', { name: 'Cancelled' }).click()

    const statusChipGroup = filterToolbar(app).getByRole('list', { name: 'Status' })
    await expect(statusChipGroup.getByText('Cancelled')).toBeVisible()

    await statusChipGroup.getByRole('button', { name: 'Close Cancelled' }).click()

    await expect(statusChipGroup).not.toBeVisible()
    await expect(filterToolbar(app).getByRole('list')).toHaveCount(0)
  })

  test('panel can be opened and closed', async ({ app }) => {
    await openRunHistoryPanel(app, workflowId!, truncatedRunId(COMPLETED_ID))

    const runHistoryHeading = app.getByRole('heading', { name: 'Run history', level: 2 })
    await expect(runHistoryHeading).toBeVisible()
    await expect(app.getByText('View past runs of this workflow.')).toBeVisible()

    await app.getByRole('button', { name: 'Close run history' }).click()

    await expect(runHistoryHeading).not.toBeVisible()
  })

  test('execution rows display run metadata', async ({ app }) => {
    await openRunHistoryPanel(app, workflowId!, truncatedRunId(COMPLETED_ID))

    const runIdText = `Run ID: ${truncatedRunId(COMPLETED_ID)}`
    await expect(app.getByText(runIdText)).toBeVisible()

    // Overlay row link is a sibling of the metadata; scope via the listitem that owns that link
    const row = app.getByRole('listitem').filter({
      has: app.getByRole('link', { name: new RegExp(runIdText) }),
    })
    await expect(row.getByText(/Elapsed time:/)).toBeVisible()
    await expect(row.getByText(/Version:/)).toBeVisible()
  })
})

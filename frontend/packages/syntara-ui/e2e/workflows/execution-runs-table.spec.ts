/**
 * E2E Tests (UI-26): Execution — Workflow Runs Table with Filtering
 * Epic: AAP-70986
 *
 * Objective: Verify the Workflow Runs list page shows executions with status and
 * timestamp columns, supports status filtering, and navigates to a detail view.
 *
 * Critical paths:
 * - Workflow Runs table shows runs with Status, Created at, Completed at columns
 * - Applying a status filter narrows results to matching executions only
 * - Clicking the Run ID navigates to the execution detail page
 *
 * beforeAll creates a workflow and one execution via API so these tests are
 * fully self-contained — no seed data dependency. afterAll deletes the workflow.
 */

import { test, expect, toAppUrl } from '../fixtures'
import { buildUniqueName } from '../helpers/workflows'
import { createWorkflowViaApi, deleteWorkflowViaApi } from '../seeds/resources'
import { apiRequest, ensureProject, getAuthToken } from '../utils/api'

let workflowId: string | null = null

test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage()
  try {
    const project = await ensureProject(page)
    const workflow = await createWorkflowViaApi(page, {
      name: buildUniqueName('e2e-ui26'),
      projectId: project?.id,
    })
    if (workflow) {
      workflowId = workflow.id
      const token = await getAuthToken(page)
      if (token) {
        await apiRequest(page, 'post', '/executions', {
          token,
          data: { workflow_id: workflowId, trigger_node_id: 'trigger_1' },
        })
      }
    }
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

test.describe('UI-26: Workflow Runs Table with Filtering', () => {
  test.beforeEach(async ({ app }) => {
    await app.goto(toAppUrl('/executions'))
    await expect(app.getByRole('heading', { level: 1, name: 'Workflow Runs' })).toBeVisible()
    await expect(app.getByRole('grid', { name: 'Executions table' })).toBeVisible()
  })

  test('workflow runs table shows runs with status and timestamp columns', async ({ app }) => {
    const table = app.getByRole('grid', { name: 'Executions table' })
    await expect(table.getByRole('columnheader', { name: 'Workflow name' })).toBeVisible()
    await expect(table.getByRole('columnheader', { name: 'Run ID' })).toBeVisible()
    await expect(table.getByRole('columnheader', { name: 'Status' })).toBeVisible()
    await expect(table.getByRole('columnheader', { name: 'Created at' })).toBeVisible()
    await expect(table.getByRole('columnheader', { name: 'Completed at' })).toBeVisible()

    // At least one data row must be present (created in beforeAll).
    // Exclude the header row — `tbody tr:first-child` can match a hidden PF control row.
    const dataRows = table.getByRole('row').filter({ hasNot: table.getByRole('columnheader') })
    await expect(dataRows).not.toHaveCount(0)
  })

  test('status filter narrows results to matching executions', async ({ app }) => {
    // Switch the filter field from "Workflow name" to "Status"
    await app
      .getByRole('search', { name: 'Filters' })
      .getByRole('button', { name: 'Workflow name', exact: true })
      .click()
    await app.getByRole('option', { name: 'Status' }).click()

    // Apply the "Completed" status filter (executions created in beforeAll are completed)
    await app.getByRole('button', { name: 'Filter by status' }).click()
    await app.getByRole('option', { name: 'Completed', exact: true }).click()

    // Filter chip must appear
    const statusChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Status' })
    await expect(statusChipGroup).toBeVisible()
    await expect(statusChipGroup.getByText('Completed')).toBeVisible()

    // URL reflects the filter
    await expect(app).toHaveURL(/status=completed/)

    // Table must show only completed executions. Scope to data rows (exclude the
    // header row) so "Completed at" column header text can't cause false positives.
    const table = app.getByRole('grid', { name: 'Executions table' })
    const dataRows = table.getByRole('row').filter({ hasNot: table.getByRole('columnheader') })
    await expect(dataRows.filter({ hasText: 'Completed' })).not.toHaveCount(0)
    await expect(dataRows.filter({ hasText: 'Failed' })).toHaveCount(0)
    await expect(dataRows.filter({ hasText: 'Running' })).toHaveCount(0)

    // Clear the filter — the Status group is single-select so there is exactly
    // one chip and one close button within statusChipGroup
    await statusChipGroup.getByRole('button', { name: /close/i }).click()
    await expect(statusChipGroup).not.toBeVisible()
    await expect(app).not.toHaveURL(/status=completed/)
  })

  test('clicking the Run ID navigates to the execution detail page', async ({ app }) => {
    // Filter to our test workflow so exactly one Run ID button is in the table
    expect(workflowId, 'workflowId must be set by beforeAll').not.toBeNull()
    await app.goto(toAppUrl(`/executions?workflow_id=${workflowId!}`))
    await expect(app.getByRole('heading', { level: 1, name: 'Workflow Runs' })).toBeVisible()

    const table = app.getByRole('grid', { name: 'Executions table' })

    // Run ID buttons are the only buttons in the table whose text is rendered
    // inside a <code> element — distinct from the Workflow name button in the
    // same row. Same pattern as executions.spec.ts.
    const runIdLink = table.getByRole('link').filter({ has: app.locator('code') })
    await expect(runIdLink).toHaveCount(1)
    await runIdLink.click()

    // Must navigate to the execution detail page
    await expect(app).toHaveURL(/\/executions\//)
    await expect(app.getByRole('heading', { level: 1 })).toBeVisible()
  })
})

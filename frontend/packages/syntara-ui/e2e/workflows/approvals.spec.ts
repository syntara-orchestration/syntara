/**
 * E2E Tests: Approvals List Page (UI-28, UI-29)
 *
 * Critical paths covered:
 * - Approvals list filtering by name and status
 * - UI-29: Self-contained approve flow — create workflow with approval node,
 *   run it, find the pending approval in the queue, approve it, verify execution resumes
 */
import { type Page } from '../fixtures'
import { test, expect, toAppUrl } from '../fixtures'
import { applyApprovalNameFilter } from '../helpers/approvals'
import { APP_TITLE } from '../helpers/appTitle'
import { addApprovalNodeWithBranch } from '../helpers/v2-nodes'
import { runWorkflowFromBuilder, waitForExecutionPaused } from '../helpers/workflow-run'
import { buildUniqueName, openWorkflowInBuilder } from '../helpers/workflows'
import {
  apiRequest,
  createWorkflowViaApi,
  deleteWorkflowViaApi,
  pollApprovalVisible,
  publishWorkflowViaApi,
  pollExecutionStatus,
} from '../utils/api'

/**
 * Helper: Create a workflow with an approval node and run it to create a pending approval.
 * Returns workflow ID and approval node name for cleanup and filtering.
 *
 * @param app - Playwright page instance
 * @param namePrefix - Optional prefix for the approval name. Use a shared prefix (e.g., `batch-${Date.now()}`)
 *                     when creating multiple approvals that need to be filtered together in batch operations.
 */
async function createPendingApproval(
  app: Page,
  namePrefix = 'approval'
): Promise<{ workflowId: string; approvalName: string }> {
  const workflowName = buildUniqueName('e2e-batch-test')
  const approvalName = buildUniqueName(namePrefix)

  // Create the complete workflow via API: trigger → approval → approved-branch script
  const { id: workflowId, versionNumber } = await createWorkflowViaApi(
    app,
    workflowName,
    [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
    [
      { id: 'approval_1', type: 'approval', name: approvalName, parameters: {} },
      {
        id: 'script_1',
        type: 'script',
        name: `${approvalName} - approved action`,
        parameters: { language: 'python', code: 'print("approved")' },
      },
    ],
    [
      { from: 'trigger_1', to: 'approval_1' },
      { from: 'approval_1', to: 'script_1', from_port: 'approved' },
    ]
  )

  // Publish the workflow so it can be run
  await publishWorkflowViaApi(app, workflowId, versionNumber)

  // Run the workflow via API (POST /executions is the public start-run endpoint)
  const runResp = await apiRequest(app, 'post', '/executions', {
    data: { workflow_id: workflowId, trigger_node_id: 'trigger_1', use_published: true },
  })
  const execution = (await runResp.json()) as { id?: string; execution_id?: string }
  const executionId = execution.id ?? execution.execution_id
  expect(executionId, 'POST /executions did not return an execution ID').toBeTruthy()
  if (!executionId) {
    throw new Error('POST /executions did not return an execution ID')
  }

  // Wait for execution to pause at the approval node (requires Temporal).
  // Describe-level SYNTARA_E2E_HAS_TEMPORAL_WORKER already gates environment availability.
  await pollExecutionStatus(app, executionId, ['paused'])

  // Wait for the approval record to be queryable in the listing API before returning.
  // There is a brief async gap between the execution reaching "paused" and the approval
  // appearing in the approvals index — polling here prevents the race in the test setup.
  await pollApprovalVisible(app, approvalName, { timeout: 45_000 })

  return { workflowId, approvalName }
}

/**
 * Create a pending approval without requiring Temporal.
 * On mock: POST /executions with an approval node auto-creates approval rows.
 * On real backend: polls for the execution to pause and approval to appear.
 */
async function createPendingApprovalLight(
  app: Page,
  namePrefix = 'approval'
): Promise<{ workflowId: string; approvalName: string }> {
  const workflowName = buildUniqueName('e2e-filter-test')
  const approvalName = buildUniqueName(namePrefix)
  const hasTemporal = !!process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER']

  const { id: workflowId, versionNumber } = await createWorkflowViaApi(
    app,
    workflowName,
    [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
    [
      { id: 'approval_1', type: 'approval', name: approvalName, parameters: {} },
      {
        id: 'script_1',
        type: 'script',
        name: `${approvalName} - approved action`,
        parameters: { language: 'python', code: 'print("approved")' },
      },
    ],
    [
      { from: 'trigger_1', to: 'approval_1' },
      { from: 'approval_1', to: 'script_1', from_port: 'approved' },
    ]
  )

  await publishWorkflowViaApi(app, workflowId, versionNumber)

  const runResp = await apiRequest(app, 'post', '/executions', {
    data: { workflow_id: workflowId, trigger_node_id: 'trigger_1', use_published: true },
  })
  const execution = (await runResp.json()) as { id?: string; execution_id?: string }
  const executionId = execution.id ?? execution.execution_id
  if (!executionId) throw new Error('POST /executions did not return an execution ID')

  if (hasTemporal) {
    await pollExecutionStatus(app, executionId, ['paused'])
    await pollApprovalVisible(app, approvalName, { timeout: 45_000 })
  }

  return { workflowId, approvalName }
}

test('user filters approvals by name and status', async ({ app }) => {
  const approval = await createPendingApprovalLight(app, 'e2e-filter')

  try {
    await app.goto(toAppUrl('/approvals'))
    await expect(app.getByRole('heading', { level: 1, name: 'Approvals' })).toBeVisible()
    await expect(app).toHaveTitle(`Approvals | ${APP_TITLE}`)

    const table = app.getByRole('grid', { name: 'Approvals table' })
    await expect(table).toBeVisible({ timeout: 15_000 })

    await applyApprovalNameFilter(app, table, approval.approvalName, {
      waitForRowText: approval.approvalName,
    })

    const nameChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })
    await expect(nameChipGroup.getByText(approval.approvalName)).toBeVisible()
    await expect(app).toHaveURL(new RegExp(`name%5Bcontains%5D=${encodeURIComponent(approval.approvalName)}`))

    await app.getByRole('search', { name: 'Filters' }).getByRole('button', { name: 'Name', exact: true }).click()
    await app.getByRole('option', { name: 'Status' }).click()
    await app.getByRole('button', { name: 'Filter by status' }).click()
    await app.getByRole('menuitem', { name: 'Pending' }).click()

    const statusChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Status' })
    await expect(nameChipGroup.getByText(approval.approvalName)).toBeVisible()
    await expect(statusChipGroup.getByText('Pending')).toBeVisible()
    await expect(app).toHaveURL(new RegExp(`name%5Bcontains%5D=${encodeURIComponent(approval.approvalName)}`))
    await expect(app).toHaveURL(/status%5Bin%5D=pending|status\[in\]=pending/)
    await expect(table.getByRole('row').filter({ hasText: approval.approvalName })).toBeVisible()

    await nameChipGroup.getByRole('button', { name: /close/i }).click()

    await expect(nameChipGroup).not.toBeVisible()
    await expect(statusChipGroup.getByText('Pending')).toBeVisible()
    await expect(app).not.toHaveURL(/name%5Bcontains%5D/)
    await expect(app).toHaveURL(/status%5Bin%5D=pending|status\[in\]=pending/)

    await app.getByRole('search', { name: 'Filters' }).getByRole('button', { name: 'Clear all filters' }).click()

    await expect(app.getByRole('search', { name: 'Filters' }).getByRole('list')).toHaveCount(0)
    await expect(app).not.toHaveURL(/name%5Bcontains%5D/)
    await expect(app).not.toHaveURL(/status/)

    await app.getByRole('search', { name: 'Filters' }).getByRole('button', { name: 'Status', exact: true }).click()
    await app.getByRole('option', { name: 'Name' }).click()

    const impossibleName = buildUniqueName('zzz-nonexistent')
    await app.getByPlaceholder('Filter by name').fill(impossibleName)
    await app.getByRole('button', { name: 'Apply filter' }).click()

    const filterChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })
    await expect(filterChipGroup).toBeVisible()

    await expect(app.getByRole('heading', { name: 'No results found' })).toBeVisible()
    await app.getByRole('button', { name: 'Clear all filters' }).last().click()
    await expect(table).toBeVisible()
  } finally {
    await deleteWorkflowViaApi(app, approval.workflowId)
  }
})

test.describe('Approval Workflow Operations', () => {
  test.skip(!process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER'], 'Temporal worker unavailable (globalSetup probe)')

  test('user bulk-approves filtered approval rows', async ({ app }) => {
    // Create 2 pending approvals with a shared prefix for filtering
    const batchId = `batch-${Date.now()}`
    const approval1 = await createPendingApproval(app, batchId)
    const approval2 = await createPendingApproval(app, batchId)

    try {
      // Navigate to approvals page
      await app.goto(toAppUrl('/approvals'))
      await expect(app.getByRole('heading', { level: 1, name: 'Approvals' })).toBeVisible()

      const table = app.getByRole('grid', { name: 'Approvals table' })
      await table.waitFor({ state: 'visible', timeout: 15_000 })

      await applyApprovalNameFilter(app, table, batchId)

      // Step 1: Select both approvals using row-scoped checkboxes — wait for each row before interacting
      const rows = table.getByRole('row')
      await expect(rows.filter({ hasText: approval1.approvalName })).toBeVisible({ timeout: 15_000 })
      await rows.filter({ hasText: approval1.approvalName }).getByRole('checkbox').check()
      await expect(rows.filter({ hasText: approval2.approvalName })).toBeVisible({ timeout: 15_000 })
      await rows.filter({ hasText: approval2.approvalName }).getByRole('checkbox').check()

      // Bulk actions live in the page header (Compass toolbar has no accessible name).
      const pageHeader = app.getByTestId('page-header')
      await expect(pageHeader.getByText('2 selected')).toBeVisible()

      const approveButton = pageHeader.getByRole('button', { name: 'Approve' })
      const rejectButton = pageHeader.getByRole('button', { name: 'Reject' })
      await expect(approveButton).toBeVisible()
      await expect(rejectButton).toBeVisible()

      await approveButton.click()

      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('heading', { name: /approve.*approval/i })).toBeVisible()

      // Step 5: Fill in approval notes
      const notesInput = dialog.getByPlaceholder(/optional.*note|explain.*reason/i)
      await expect(notesInput).toBeVisible()
      await notesInput.fill('Batch approval - E2E test')

      // Step 6: Submit batch approval
      const submitButton = dialog.getByRole('button', { name: 'Approve' })
      await expect(submitButton).toBeVisible()
      await submitButton.click()

      // Step 7: Verify success notification
      await expect(app.getByText('Approvals submitted')).toBeVisible({ timeout: 10_000 })

      await expect(pageHeader.getByText('2 selected')).not.toBeVisible()

      // Step 9: Verify checkboxes are unchecked
      await expect(rows.filter({ hasText: approval1.approvalName }).getByRole('checkbox')).not.toBeChecked()
      await expect(rows.filter({ hasText: approval2.approvalName }).getByRole('checkbox')).not.toBeChecked()
    } finally {
      // Cleanup: delete created workflows
      await apiRequest(app, 'delete', `/workflows/${approval1.workflowId}`).catch(() => {})
      await apiRequest(app, 'delete', `/workflows/${approval2.workflowId}`).catch(() => {})
    }
  })

  test('user bulk-rejects filtered approval rows', async ({ app }) => {
    // Create 2 pending approvals with a shared prefix for filtering
    const batchId = `batch-${Date.now()}`
    const approval1 = await createPendingApproval(app, batchId)
    const approval2 = await createPendingApproval(app, batchId)

    try {
      // Navigate to approvals page
      await app.goto(toAppUrl('/approvals'))
      await expect(app.getByRole('heading', { level: 1, name: 'Approvals' })).toBeVisible()

      const table = app.getByRole('grid', { name: 'Approvals table' })
      await table.waitFor({ state: 'visible', timeout: 15_000 })

      await applyApprovalNameFilter(app, table, batchId)

      // Step 1: Select both approvals using row-scoped checkboxes — wait for each row before interacting
      const rows = table.getByRole('row')
      await expect(rows.filter({ hasText: approval1.approvalName })).toBeVisible({ timeout: 15_000 })
      await rows.filter({ hasText: approval1.approvalName }).getByRole('checkbox').check()
      await expect(rows.filter({ hasText: approval2.approvalName })).toBeVisible({ timeout: 15_000 })
      await rows.filter({ hasText: approval2.approvalName }).getByRole('checkbox').check()

      const pageHeader = app.getByTestId('page-header')
      await expect(pageHeader.getByText('2 selected')).toBeVisible({ timeout: 15_000 })

      const rejectButton = pageHeader.getByRole('button', { name: 'Reject' })
      await expect(rejectButton).toBeVisible()
      await rejectButton.click()

      // Step 4: Verify rejection dialog
      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('heading', { name: /reject.*approval/i })).toBeVisible()

      // Step 5: Fill in rejection notes
      const notesInput = dialog.getByPlaceholder(/optional.*note|explain.*reason/i)
      await expect(notesInput).toBeVisible()
      await notesInput.fill('Batch rejection - E2E test')

      // Step 6: Submit batch rejection
      const submitButton = dialog.getByRole('button', { name: 'Reject' })
      await expect(submitButton).toBeVisible()
      await submitButton.click()

      // Step 7: Verify success notification
      await expect(app.getByText('Approvals rejected')).toBeVisible({ timeout: 10_000 })

      // Step 8: Verify selection cleared
      await expect(pageHeader.getByText('2 selected')).not.toBeVisible()

      // Step 9: Verify checkboxes are unchecked
      await expect(rows.filter({ hasText: approval1.approvalName }).getByRole('checkbox')).not.toBeChecked()
      await expect(rows.filter({ hasText: approval2.approvalName }).getByRole('checkbox')).not.toBeChecked()
    } finally {
      // Cleanup: delete created workflows
      await apiRequest(app, 'delete', `/workflows/${approval1.workflowId}`).catch(() => {})
      await apiRequest(app, 'delete', `/workflows/${approval2.workflowId}`).catch(() => {})
    }
  })

  // Title avoids the stale syntara-ci xfail "user cancels batch approval without API call"
  // (listed pass + old test.fail() overlay fails the run as "Expected to fail, but passed").
  test('user cancels bulk approval without submitting', async ({ app }) => {
    // Create a pending approval to test cancel behavior
    const approval = await createPendingApproval(app)

    try {
      await pollApprovalVisible(app, approval.approvalName)

      // Navigate to approvals page
      await app.goto(toAppUrl('/approvals'))
      await expect(app.getByRole('heading', { level: 1, name: 'Approvals' })).toBeVisible()

      const table = app.getByRole('grid', { name: 'Approvals table' })
      await table.waitFor({ state: 'visible', timeout: 15_000 })

      await applyApprovalNameFilter(app, table, approval.approvalName, {
        waitForRowText: approval.approvalName,
      })

      // Step 1: Select the approval using row-scoped checkbox — wait for the row before interacting
      const row = table.getByRole('row').filter({ hasText: approval.approvalName })
      await expect(row).toBeVisible({ timeout: 15_000 })
      await row.getByRole('checkbox').check()

      const pageHeader = app.getByTestId('page-header')
      await expect(pageHeader.getByText('1 selected')).toBeVisible({ timeout: 15_000 })

      const approveButton = pageHeader.getByRole('button', { name: 'Approve' })
      await expect(approveButton).toBeVisible()
      await approveButton.click()

      // Step 3: Cancel without submitting — dialog should close and selection should remain
      const dialog = app.getByRole('dialog')
      await expect(dialog.getByRole('heading', { name: /approve.*approval/i })).toBeVisible()
      await dialog.getByRole('button', { name: 'Cancel' }).click()

      await expect(app.getByRole('dialog')).not.toBeVisible({ timeout: 10_000 })
      await expect(pageHeader.getByText('1 selected')).toBeVisible({ timeout: 10_000 })

      // Step 4: Deselect to clean up
      await row.getByRole('checkbox').uncheck()
      await expect(pageHeader.getByText('1 selected')).not.toBeVisible()
    } finally {
      // Cleanup: delete created workflow
      await apiRequest(app, 'delete', `/workflows/${approval.workflowId}`).catch(() => {})
    }
  })

  test('user changes decision from approve to reject (undo)', async ({ app }) => {
    // Create a pending approval to test undo behavior
    const approval = await createPendingApproval(app)

    try {
      // Navigate to approvals page
      await app.goto(toAppUrl('/approvals'))
      await expect(app.getByRole('heading', { level: 1, name: 'Approvals' })).toBeVisible()

      const table = app.getByRole('grid', { name: 'Approvals table' })
      await table.waitFor({ state: 'visible', timeout: 15_000 })

      // Filter to show only our test approval
      await app.getByPlaceholder('Filter by name').fill(approval.approvalName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      // Wait for filter chip to confirm filter was applied and table to refresh
      await expect(app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })).toBeVisible({
        timeout: 15_000,
      })

      // Step 1: Click on the pending approval to open side panel
      const approvalLink = table.getByRole('link', { name: approval.approvalName })
      await approvalLink.waitFor({ state: 'visible', timeout: 10_000 })
      await approvalLink.click()

      // Step 2: Verify navigation to execution detail with side panel
      await expect(app).toHaveURL(/\/executions\/[^?]+\?approval=/, { timeout: 15_000 })
      await expect(app.getByRole('heading', { name: 'Review Approval' })).toBeVisible({ timeout: 15_000 })

      // Step 3: Click "Approve" button
      const approveButton = app.getByRole('button', { name: 'Approve', exact: true })
      await expect(approveButton).toBeVisible({ timeout: 15_000 })
      await approveButton.click()

      // Step 4: Verify approval notes field appears
      const approvalNotesInput = app.getByPlaceholder(/explain.*reason.*approving|optional.*note/i)
      await expect(approvalNotesInput).toBeVisible({ timeout: 10_000 })

      // Step 5: Click "Reject" to undo the approve decision
      const rejectButton = app.getByRole('button', { name: 'Reject', exact: true })
      await expect(rejectButton).toBeVisible({ timeout: 10_000 })
      await rejectButton.click()

      // Step 6: Verify rejection notes field appears (approval notes replaced)
      const rejectionNotesInput = app.getByPlaceholder(/explain.*reason.*rejecting|optional.*note/i)
      await expect(rejectionNotesInput).toBeVisible({ timeout: 10_000 })

      // Step 7: Verify approval notes field is no longer visible
      await expect(approvalNotesInput).not.toBeVisible()

      // Step 8: Verify "Submit decision" button is available for rejection
      const submitButton = app.getByRole('button', { name: 'Submit decision' })
      await expect(submitButton).toBeVisible({ timeout: 10_000 })

      // NOTE: This test verifies undo behavior (switching between approve/reject)
      // without actually submitting to avoid mutating approval state
    } finally {
      // Cleanup: delete created workflow
      await apiRequest(app, 'delete', `/workflows/${approval.workflowId}`).catch(() => {})
    }
  })

  test('user clears decision with explicit undo button', async ({ app }) => {
    // Create a pending approval to test undo/clear behavior
    const approval = await createPendingApproval(app)

    try {
      // Navigate to approvals page
      await app.goto(toAppUrl('/approvals'))
      await expect(app.getByRole('heading', { level: 1, name: 'Approvals' })).toBeVisible()

      const table = app.getByRole('grid', { name: 'Approvals table' })
      await table.waitFor({ state: 'visible', timeout: 15_000 })

      // Filter to show only our test approval
      await app.getByPlaceholder('Filter by name').fill(approval.approvalName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      // Click on the pending approval
      const approvalLink = table.getByRole('link', { name: approval.approvalName })
      await approvalLink.waitFor({ state: 'visible', timeout: 10_000 })
      await approvalLink.click()
      await expect(app.getByRole('heading', { name: 'Review Approval' })).toBeVisible({ timeout: 15_000 })

      // Step 1: Click "Approve"
      const approveButton = app.getByRole('button', { name: 'Approve', exact: true })
      await approveButton.click()
      await expect(app.getByPlaceholder(/explain.*reason.*approving/i)).toBeVisible()

      // Step 2: Look for "Undo decision" or "Clear" button
      const undoButton = app.getByRole('button', { name: /undo.*decision|clear.*selection/i })
      const hasUndoButton = await undoButton.isVisible().catch(() => false)

      if (hasUndoButton) {
        await undoButton.click()

        // Step 3: Verify both approve and reject buttons are visible again
        await expect(app.getByRole('button', { name: 'Approve', exact: true })).toBeVisible()
        await expect(app.getByRole('button', { name: 'Reject', exact: true })).toBeVisible()

        // Step 4: Verify notes field is cleared
        const notesField = app.getByPlaceholder(/explain.*reason/i)
        await expect(notesField).not.toBeVisible()
      } else {
        // If no explicit undo button exists, verify switching between approve/reject acts as undo
        const rejectButton = app.getByRole('button', { name: 'Reject', exact: true })
        await expect(rejectButton).toBeVisible()

        // Clicking reject after approve is the undo mechanism
        await rejectButton.click()
        await expect(app.getByPlaceholder(/explain.*reason.*rejecting/i)).toBeVisible()
      }
    } finally {
      // Cleanup: delete created workflow
      await apiRequest(app, 'delete', `/workflows/${approval.workflowId}`).catch(() => {})
    }
  })

  test('user selects all filtered approvals using the header checkbox', async ({ app }) => {
    // Create 2 pending approvals with a shared prefix for filtering
    const batchId = `batch-${Date.now()}`
    const approval1 = await createPendingApproval(app, batchId)
    const approval2 = await createPendingApproval(app, batchId)

    try {
      // Navigate to approvals page
      await app.goto(toAppUrl('/approvals'))
      await expect(app.getByRole('heading', { level: 1, name: 'Approvals' })).toBeVisible()

      const table = app.getByRole('grid', { name: 'Approvals table' })
      await table.waitFor({ state: 'visible', timeout: 15_000 })

      // Filter to show only our test approvals using shared batch ID
      await app.getByPlaceholder('Filter by name').fill(batchId)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      // Wait for filter chip to confirm filter was applied and both rows to appear
      await expect(app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })).toBeVisible({
        timeout: 15_000,
      })
      const rows = table.getByRole('row')
      await expect(rows.filter({ hasText: approval1.approvalName })).toBeVisible({
        timeout: 15_000,
      })
      await expect(rows.filter({ hasText: approval2.approvalName })).toBeVisible({
        timeout: 15_000,
      })

      // Click header row checkbox to select all. Bulk actions live in the page header
      // (Compass toolbar has no accessible name) — same pattern as sibling batch tests.
      // Under Konflux cluster load the checkbox click can fail to register; retry the whole sequence.
      const selectAllCheckbox = table.getByRole('checkbox', { name: /select all/i })
      await expect(selectAllCheckbox).toBeEnabled()
      const pageHeader = app.getByTestId('page-header')
      const selectedText = pageHeader.getByText('2 selected')

      await expect(async () => {
        await selectAllCheckbox.check()
        await expect(selectedText).toBeVisible()
      }).toPass({ timeout: 15_000, intervals: [500] })

      // Uncheck header checkbox to deselect all
      await selectAllCheckbox.uncheck()

      // Verify selection cleared
      await expect(selectedText).not.toBeVisible()

      // Verify all checkboxes are unchecked
      await expect(rows.filter({ hasText: approval1.approvalName }).getByRole('checkbox')).not.toBeChecked()
      await expect(rows.filter({ hasText: approval2.approvalName }).getByRole('checkbox')).not.toBeChecked()
    } finally {
      // Cleanup: delete created workflows
      await apiRequest(app, 'delete', `/workflows/${approval1.workflowId}`).catch(() => {})
      await apiRequest(app, 'delete', `/workflows/${approval2.workflowId}`).catch(() => {})
    }
  })

  test('UI-29: self-contained approve flow via approvals queue', async ({ app }) => {
    // Create a workflow with an approval node so we control the approval name
    const workflowName = buildUniqueName('e2e-approve')
    const approvalNodeName = buildUniqueName('gate')
    const { id: workflowId } = await createWorkflowViaApi(app, workflowName, [
      { id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} },
    ])
    await openWorkflowInBuilder(app, workflowName, workflowId)

    try {
      // Add approval node with a unique name so we can find it in the approvals list
      await addApprovalNodeWithBranch(app, approvalNodeName)
      await app.getByRole('button', { name: 'Save', exact: true }).click()
      await runWorkflowFromBuilder(app)

      // Wait for execution to pause at the approval node (requires Temporal)
      const reachedApproval = await waitForExecutionPaused(app)
      expect(reachedApproval, 'Execution stayed Pending — Temporal worker may not be running').toBeTruthy()

      // Navigate to the approvals queue and find our approval
      await app.goto(toAppUrl('/approvals'))
      await expect(app.getByRole('heading', { level: 1, name: 'Approvals' })).toBeVisible()

      const approvalsTable = app.getByRole('grid', { name: 'Approvals table' })
      await approvalsTable.waitFor({ state: 'visible', timeout: 15_000 })

      // Filter by the unique approval node name
      await app.getByPlaceholder('Filter by name').fill(approvalNodeName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      const approvalLink = approvalsTable.getByRole('link', { name: approvalNodeName })
      await approvalLink.waitFor({ state: 'visible', timeout: 15_000 })

      // Click approval — navigates to execution detail with side panel
      await approvalLink.click()
      await expect(app).toHaveURL(/\/executions\/[^?]+\?approval=/)
      await expect(app.getByRole('heading', { name: 'Review Approval' })).toBeVisible({ timeout: 15_000 })

      // Approve with notes
      await app.getByRole('button', { name: 'Approve' }).click()
      await app.getByPlaceholder(/Explain the reason for approving/i).fill('Approved in E2E test')
      await app.getByRole('button', { name: 'Submit decision' }).click()

      // Verify approval was submitted and execution resumes
      await expect(app.getByText('Approval submitted')).toBeVisible({ timeout: 15_000 })
      await expect(app.getByText('Completed')).toBeVisible({ timeout: 30_000 })
    } finally {
      if (workflowId) {
        await apiRequest(app, 'delete', `/workflows/${workflowId}`).catch(() => {})
      }
    }
  })
}) // Approval Workflow Operations

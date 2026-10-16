/**
 * E2E Tests: Approvals List Page (UI-28, UI-29)
 *
 * Critical paths covered:
 * - Approvals list filtering by name and status
 * - UI-29: Self-contained approve flow — create workflow with approval node,
 *   run it, find the pending approval in the queue, approve it, verify execution resumes
 */
import { createUnavailableGuard, type Page, test, expect, toAppUrl } from '../fixtures'
import {
  applyApprovalNameFilter,
  dismissConnectionBanner,
  expectApprovalsListPageTitle,
  getApprovalsBulkToolbar,
  gotoApprovalsList,
  navigateToApprovalAndOpen,
} from '../helpers/approvals'
import { buildUniqueName } from '../helpers/workflows'
import { isSkipWebServerForPlaywrightTests } from '../playwrightWebServerEnv'
import {
  apiRequest,
  createWorkflowViaApi,
  deleteWorkflowViaApi,
  pollApprovalVisible,
  publishWorkflowViaApi,
  pollExecutionStatus,
} from '../utils/api'

/** Temporal can be slow to reach the approval gate under CI load. */
const APPROVAL_GATE_POLL_TIMEOUT = 90_000

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
  const { id: workflowId, versionNumber } = await createWorkflowViaApi({
    app,
    name: workflowName,
    triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
    nodes: [
      { id: 'approval_1', type: 'approval', name: approvalName, parameters: {} },
      {
        id: 'script_1',
        type: 'script',
        name: `${approvalName} - approved action`,
        parameters: { language: 'python', code: 'print("approved")' },
      },
    ],
    edges: [
      { from: 'trigger_1', to: 'approval_1' },
      { from: 'approval_1', to: 'script_1', from_port: 'approved' },
    ],
  })

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

  const { id: workflowId, versionNumber } = await createWorkflowViaApi({
    app,
    name: workflowName,
    triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
    nodes: [
      { id: 'approval_1', type: 'approval', name: approvalName, parameters: {} },
      {
        id: 'script_1',
        type: 'script',
        name: `${approvalName} - approved action`,
        parameters: { language: 'python', code: 'print("approved")' },
      },
    ],
    edges: [
      { from: 'trigger_1', to: 'approval_1' },
      { from: 'approval_1', to: 'script_1', from_port: 'approved' },
    ],
  })

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
    await gotoApprovalsList(app)
    await expectApprovalsListPageTitle(app)

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

/** Mock seed row in syntara-mock-api/src/resources/approvals.ts (approved, decision_notes: null). */
const SILENT_APPROVAL_MOCK_ID = '550e8400-e29b-41d4-a716-446655440046'
const SILENT_APPROVAL_MOCK_NAME = 'Silent Approval Decision'

test.describe('Approvals list expand toggle (mock seed)', { tag: '@pr-check' }, () => {
  test.skip(
    isSkipWebServerForPlaywrightTests(),
    'Silent Approval seed exists only in syntara-mock-api (Playwright webServer)'
  )

  const seedGuard = createUnavailableGuard(
    'Mock approval seed required (Silent Approval Decision in syntara-mock-api approvals)'
  )

  test.beforeEach(async ({ app }) => {
    const seedResp = await apiRequest(app, 'get', `/approvals/${SILENT_APPROVAL_MOCK_ID}`)
    if (!seedResp.ok()) {
      seedGuard.markUnavailable()
      test.skip(true, 'Mock approval seed required (Silent Approval Decision)')
    }
  })

  test('hides row expand control when decision notes are empty', async ({ app }) => {
    await app.goto(toAppUrl('/tasks/approvals'))
    await expect(app.getByRole('heading', { level: 1, name: 'Tasks' })).toBeVisible()

    const table = app.getByRole('grid', { name: 'Approvals table' })
    await expect(table).toBeVisible({ timeout: 15_000 })

    await applyApprovalNameFilter(app, table, SILENT_APPROVAL_MOCK_NAME, {
      waitForRowText: SILENT_APPROVAL_MOCK_NAME,
    })

    const row = table.getByRole('row').filter({ hasText: SILENT_APPROVAL_MOCK_NAME })
    await expect(row.getByRole('button', { name: /details/i })).toHaveCount(0)
  })
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
      await gotoApprovalsList(app)

      const table = app.getByRole('grid', { name: 'Approvals table' })
      await table.waitFor({ state: 'visible', timeout: 15_000 })

      await applyApprovalNameFilter(app, table, batchId)

      // Step 1: Select both approvals using row-scoped checkboxes — wait for each row before interacting
      const rows = table.getByRole('row')
      await expect(rows.filter({ hasText: approval1.approvalName })).toBeVisible({ timeout: 15_000 })
      await rows.filter({ hasText: approval1.approvalName }).getByRole('checkbox').check()
      await expect(rows.filter({ hasText: approval2.approvalName })).toBeVisible({ timeout: 15_000 })
      await rows.filter({ hasText: approval2.approvalName }).getByRole('checkbox').check()

      const bulkToolbar = getApprovalsBulkToolbar(app, 2)
      await expect(bulkToolbar).toBeVisible()

      const approveButton = bulkToolbar.getByRole('button', { name: 'Approve' })
      const rejectButton = bulkToolbar.getByRole('button', { name: 'Reject' })
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

      await expect(app.getByText('2 selected')).not.toBeVisible()

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
      await gotoApprovalsList(app)

      const table = app.getByRole('grid', { name: 'Approvals table' })
      await table.waitFor({ state: 'visible', timeout: 15_000 })

      await applyApprovalNameFilter(app, table, batchId)

      // Step 1: Select both approvals using row-scoped checkboxes — wait for each row before interacting
      const rows = table.getByRole('row')
      await expect(rows.filter({ hasText: approval1.approvalName })).toBeVisible({ timeout: 15_000 })
      await rows.filter({ hasText: approval1.approvalName }).getByRole('checkbox').check()
      await expect(rows.filter({ hasText: approval2.approvalName })).toBeVisible({ timeout: 15_000 })
      await rows.filter({ hasText: approval2.approvalName }).getByRole('checkbox').check()

      const bulkToolbar = getApprovalsBulkToolbar(app, 2)
      await expect(bulkToolbar).toBeVisible({ timeout: 15_000 })

      const rejectButton = bulkToolbar.getByRole('button', { name: 'Reject' })
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
      await expect(app.getByText('2 selected')).not.toBeVisible()

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
      await gotoApprovalsList(app)

      const table = app.getByRole('grid', { name: 'Approvals table' })
      await table.waitFor({ state: 'visible', timeout: 15_000 })

      await applyApprovalNameFilter(app, table, approval.approvalName, {
        waitForRowText: approval.approvalName,
      })

      // Step 1: Select the approval using row-scoped checkbox — wait for the row before interacting
      const row = table.getByRole('row').filter({ hasText: approval.approvalName })
      await expect(row).toBeVisible({ timeout: 15_000 })
      await row.getByRole('checkbox').check()

      const bulkToolbar = getApprovalsBulkToolbar(app, 1)
      await expect(bulkToolbar).toBeVisible({ timeout: 15_000 })

      const approveButton = bulkToolbar.getByRole('button', { name: 'Approve' })
      await expect(approveButton).toBeVisible()
      await approveButton.click()

      // Step 3: Cancel without submitting — dialog should close and selection should remain
      const dialog = app.getByRole('dialog')
      await expect(dialog.getByRole('heading', { name: /approve.*approval/i })).toBeVisible()
      await dialog.getByRole('button', { name: 'Cancel' }).click()

      await expect(app.getByRole('dialog')).not.toBeVisible({ timeout: 10_000 })
      await expect(bulkToolbar).toBeVisible({ timeout: 10_000 })

      // Step 4: Deselect to clean up
      await row.getByRole('checkbox').uncheck()
      await expect(app.getByText('1 selected')).not.toBeVisible()
    } finally {
      // Cleanup: delete created workflow
      await apiRequest(app, 'delete', `/workflows/${approval.workflowId}`).catch(() => {})
    }
  })

  test('user changes decision from approve to reject (undo)', async ({ app }) => {
    test.slow()
    const approval = await createPendingApproval(app)

    try {
      await navigateToApprovalAndOpen(app, approval.approvalName)
      await dismissConnectionBanner(app)

      const approveButton = app.getByRole('button', { name: 'Approve', exact: true })
      const rejectButton = app.getByRole('button', { name: 'Reject', exact: true })
      await expect(approveButton).not.toHaveAttribute('aria-disabled', 'true', { timeout: 20_000 })

      await approveButton.click()
      await expect(app.getByPlaceholder(/Explain the reason for approving/i)).toBeVisible({ timeout: 10_000 })
      // Pending approve hides the action buttons; undo clears the draft before choosing reject.
      await expect(rejectButton).not.toBeVisible()

      await app.getByRole('button', { name: 'Undo decision' }).click()
      await expect(approveButton).toBeVisible({ timeout: 10_000 })
      await expect(rejectButton).toBeVisible({ timeout: 10_000 })
      await expect(rejectButton).not.toHaveAttribute('aria-disabled', 'true', { timeout: 20_000 })

      await rejectButton.click()
      await expect(app.getByPlaceholder(/Explain the reason for rejecting/i)).toBeVisible({ timeout: 10_000 })
      await expect(app.getByRole('button', { name: 'Submit decision' })).toBeVisible({ timeout: 10_000 })
    } finally {
      await apiRequest(app, 'delete', `/workflows/${approval.workflowId}`).catch(() => {})
    }
  })

  test('user clears decision with explicit undo button', async ({ app }) => {
    test.slow()
    const approval = await createPendingApproval(app)

    try {
      await navigateToApprovalAndOpen(app, approval.approvalName)
      await dismissConnectionBanner(app)

      const approveButton = app.getByRole('button', { name: 'Approve', exact: true })
      await expect(approveButton).not.toHaveAttribute('aria-disabled', 'true', { timeout: 20_000 })
      await approveButton.click()
      await expect(app.getByPlaceholder(/Explain the reason for approving/i)).toBeVisible({ timeout: 10_000 })

      await app.getByRole('button', { name: 'Undo decision' }).click()

      await expect(approveButton).toBeVisible({ timeout: 10_000 })
      await expect(app.getByRole('button', { name: 'Reject', exact: true })).toBeVisible()
      await expect(app.getByPlaceholder(/Explain the reason for approving/i)).not.toBeVisible()
    } finally {
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
      await gotoApprovalsList(app)

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

      // Click header row checkbox to select all. Bulk actions live in the list toolbar.
      // Under Konflux cluster load the checkbox click can fail to register; retry the whole sequence.
      const selectAllCheckbox = table.getByRole('checkbox', { name: /select all/i })
      await expect(selectAllCheckbox).toBeEnabled()
      const bulkToolbar = getApprovalsBulkToolbar(app, 2)

      await expect(async () => {
        await selectAllCheckbox.check()
        await expect(bulkToolbar).toBeVisible()
      }).toPass({ timeout: 15_000, intervals: [500] })

      // Uncheck header checkbox to deselect all
      await selectAllCheckbox.uncheck()

      // Verify selection cleared
      await expect(app.getByText('2 selected')).not.toBeVisible()

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
    test.slow()
    const workflowName = buildUniqueName('e2e-ui29')
    const approvalNodeName = buildUniqueName('gate')

    const { id: workflowId, versionNumber } = await createWorkflowViaApi({
      app,
      name: workflowName,
      triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
      nodes: [
        { id: 'approval_1', type: 'approval', name: approvalNodeName, parameters: {} },
        {
          id: 'script_1',
          type: 'script',
          name: `${approvalNodeName} - approved action`,
          parameters: { language: 'python', code: 'print("approved")' },
        },
      ],
      edges: [
        { from: 'trigger_1', to: 'approval_1' },
        { from: 'approval_1', to: 'script_1', from_port: 'approved' },
      ],
    })
    await publishWorkflowViaApi(app, workflowId, versionNumber)

    const runResp = await apiRequest(app, 'post', '/executions', {
      data: { workflow_id: workflowId, trigger_node_id: 'trigger_1', use_published: true },
    })
    expect(runResp.ok(), `POST /executions returned ${runResp.status()}`).toBeTruthy()
    const execution = (await runResp.json()) as { id?: string; execution_id?: string }
    const executionId = execution.id ?? execution.execution_id
    expect(executionId, 'POST /executions did not return an execution ID').toBeTruthy()

    try {
      await pollExecutionStatus(app, executionId!, ['paused'], { timeout: APPROVAL_GATE_POLL_TIMEOUT })
      await pollApprovalVisible(app, approvalNodeName, { timeout: 45_000 })

      await gotoApprovalsList(app)

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
      await expect(app.getByRole('heading', { name: 'Review approval' })).toBeVisible({ timeout: 15_000 })

      const approvalIdFromUrl = new URL(app.url()).searchParams.get('approval')
      expect(approvalIdFromUrl, 'Expected ?approval= on execution detail URL').toBeTruthy()

      // Approve with notes (exact: true — workflow link names must not substring-match)
      await app.getByRole('button', { name: 'Approve', exact: true }).click()
      await app.getByPlaceholder(/Explain the reason for approving/i).fill('Approved in E2E test')
      const submitDecision = app.getByRole('button', { name: 'Submit decision' })
      await expect(submitDecision).toBeEnabled()

      const [patchResponse] = await Promise.all([
        app.waitForResponse(
          (response) =>
            response.request().method() === 'PATCH' &&
            response.url().includes(`/approvals/${approvalIdFromUrl}`) &&
            response.ok(),
          { timeout: 30_000 }
        ),
        submitDecision.click(),
      ])

      const decisionBody = (await patchResponse.json()) as { status?: string }
      expect(decisionBody.status).toBe('approved')
      await expect(app.getByText('Approval submitted')).toBeVisible({ timeout: 15_000 })

      if (isSkipWebServerForPlaywrightTests()) {
        // Live stack: wait for Temporal to finish the run after the decide signal.
        await pollExecutionStatus(app, executionId!, ['completed', 'completed_with_errors', 'failed', 'cancelled'], {
          timeout: APPROVAL_GATE_POLL_TIMEOUT,
        })
        await app.reload()
        await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
        await expect(app.getByTestId('execution-status-badge').getByText('Completed')).toBeVisible({
          timeout: 30_000,
        })
      }
    } finally {
      if (workflowId) {
        await apiRequest(app, 'delete', `/workflows/${workflowId}`).catch(() => {})
      }
    }
  })
}) // Approval Workflow Operations

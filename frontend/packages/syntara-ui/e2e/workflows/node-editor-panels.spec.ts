import { test, expect, toAppUrl } from '../fixtures'
import { addAgenticNode, addManualTrigger, addScriptNode } from '../helpers/v2-nodes'
import {
  buildUniqueName,
  clickAddConnectedStep,
  closeNodeEditorPanel,
  createBasicWorkflowViaApi,
  openWorkflowInBuilder,
  fillCodeEditor,
  selectProjectIfRequired,
} from '../helpers/workflows'

/**
 * Wait for a PF6 dropdown item to finish animating in, then click it.
 * PF6 menus animate open after the toggle click — clicking before the item is
 * stable causes "element detached from DOM" / "not stable" errors in strict mode.
 */
async function clickMenuItemWhenVisible(app: import('@playwright/test').Page, itemName: string) {
  const item = app.getByRole('menuitem', { name: itemName })
  await expect(item).toBeVisible()
  await item.click()
}

/** Click the Layout button to reposition nodes within the viewport. */
async function layoutCanvas(app: import('@playwright/test').Page) {
  const layoutButton = app.getByRole('button', { name: 'Reset layout', exact: true })
  if ((await layoutButton.count()) > 0) {
    await layoutButton.click()
    await app.waitForSelector('[role="group"][aria-roledescription="node"]', { state: 'visible', timeout: 5_000 })
  }
  // Fit view so all nodes and edge buttons are visible in the viewport
  const fitViewButton = app.getByRole('button', { name: 'Fit view' })
  if ((await fitViewButton.count()) > 0) {
    await fitViewButton.click()
    await app.waitForTimeout(500)
  }
}

/** Click a React Flow node by its visible text label. */
async function clickNode(app: import('@playwright/test').Page, nodeText: string) {
  await layoutCanvas(app)
  const node = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: nodeText })
  await expect(node).toBeVisible({ timeout: 5_000 })
  await node.click()
}

test.describe('Node editor panels', () => {
  test('three-panel layout renders with empty states on node click', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-panels')
    const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Process data')
    await openWorkflowInBuilder(app, workflowName, id)

    // Open the script node editor
    await clickNode(app, 'Process data')

    // Verify three-panel layout — Input and Output headings
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).toBeVisible({ timeout: 10_000 })
    await expect(app.getByRole('heading', { name: 'Output', exact: true })).toBeVisible()

    // Verify Parameters section has tabs
    await expect(app.getByRole('tab', { name: 'Parameters' })).toBeVisible()
    await expect(app.getByRole('tab', { name: 'Settings' })).toBeVisible()

    // Output panel: no execution data → "No output data"
    await expect(app.getByText('No output data')).toBeVisible()
    await expect(app.getByText('Run the workflow or test this step to see output data here.')).toBeVisible()

    // Verify the close button works
    await closeNodeEditorPanel(app)
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).not.toBeVisible()
  })

  test('node editor can be opened, closed, and reopened', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-reopen')
    const { id } = await createBasicWorkflowViaApi(app, workflowName, 'My action')
    await openWorkflowInBuilder(app, workflowName, id)

    // Click the script node to open the editor
    await clickNode(app, 'My action')

    // Verify the editor is open
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).toBeVisible({ timeout: 10_000 })
    await expect(app.getByRole('heading', { name: 'Output', exact: true })).toBeVisible()

    // Close the editor
    await closeNodeEditorPanel(app)
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).not.toBeVisible()

    // Click the trigger node — triggers do NOT show the Input panel
    await clickNode(app, 'Manual trigger')
    await expect(app.getByRole('heading', { name: 'Output', exact: true })).toBeVisible({ timeout: 10_000 })

    // Close and reopen the script node
    await closeNodeEditorPanel(app)
    await clickNode(app, 'My action')
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).toBeVisible({ timeout: 10_000 })
    await expect(app.getByRole('heading', { name: 'Output', exact: true })).toBeVisible()
  })

  test('output panel displays execution data', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-output')
    const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Run script')
    await openWorkflowInBuilder(app, workflowName, id)

    // Extract node IDs and workflow ID
    const scriptNode = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Run script' })
    await expect(scriptNode).toBeVisible()
    const scriptNodeId = await scriptNode.getAttribute('data-id')
    const workflowId = app.url().split('/').pop()

    // Mock execution data via route interception
    await app.route(/\/api\/v1\/executions/, async (route) => {
      const url = route.request().url()

      if (url.includes('/activities')) {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            resources: [
              {
                id: 'act-script-out',
                execution_id: 'e2e-exec-2',
                activity_name: scriptNodeId,
                status: 'completed',
                started_at: '2024-01-01T00:00:30Z',
                completed_at: '2024-01-01T00:01:00Z',
                output_data: {
                  message: 'Script executed successfully',
                  exit_code: 0,
                },
                input_data: {},
                error_details: null,
                retry_count: 0,
                iteration: null,
              },
            ],
            next: null,
            prev: null,
          }),
        })
      } else {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            resources: [
              {
                id: 'e2e-exec-2',
                workflow_id: workflowId,
                status: 'completed',
                started_at: '2024-01-01T00:00:00Z',
                completed_at: '2024-01-01T00:01:00Z',
                created_at: '2024-01-01T00:00:00Z',
              },
            ],
            next: null,
            prev: null,
          }),
        })
      }
    })

    // Click the script node
    await clickNode(app, 'Run script')

    // Verify output panel shows execution data instead of empty state
    await expect(app.getByRole('heading', { name: 'Output', exact: true })).toBeVisible({ timeout: 10_000 })
    await expect(app.getByText('"message"')).toBeVisible({ timeout: 10_000 })
    await expect(app.getByText('"Script executed successfully"')).toBeVisible()
    // The empty state text should NOT be visible
    await expect(app.getByText('No output data')).not.toBeVisible()
  })

  test('output data flows through a 4-node chain', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-chain')

    // Build: Trigger → Gather Info → Process Data → Send Alert
    await app.goto(toAppUrl('/workflow-builder/new'))
    await addManualTrigger(app, 'Trigger')
    await addScriptNode(
      app,
      'Gather Info',
      'import json; print(json.dumps({"server": "web-01", "status": "degraded", "cpu": 92, "errors": 15}))'
    )
    await addScriptNode(
      app,
      'Process Data',
      'import json, sys; print(json.dumps({"alert_level": "warning", "affected_server": data["server"]}))'
    )
    await addScriptNode(
      app,
      'Send Alert',
      'import json; print(json.dumps({"notification_sent": True, "channel": "#ops-alerts"}))'
    )

    // Extract node IDs from the canvas before saving (IDs are stable across save)
    await layoutCanvas(app)
    const gatherNode = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Gather Info' })
    const processNode = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Process Data' })
    const alertNode = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Send Alert' })
    await expect(gatherNode).toBeVisible({ timeout: 5_000 })

    const gatherNodeId = await gatherNode.getAttribute('data-id')
    const processNodeId = await processNode.getAttribute('data-id')
    const alertNodeId = await alertNode.getAttribute('data-id')

    // Realistic execution output — what Temporal produces for each script node
    const gatherOutputData = {
      status: 'completed',
      stderr: '',
      return_code: 0,
      stdout: '{"server": "web-01", "status": "degraded", "cpu": 92, "errors": 15}\n',
      stdout_json: { server: 'web-01', status: 'degraded', cpu: 92, errors: 15 },
    }
    const processOutputData = {
      status: 'completed',
      stderr: '',
      return_code: 0,
      stdout: '{"alert_level": "warning", "affected_server": "web-01", "cpu_exceeded": true}\n',
      stdout_json: { alert_level: 'warning', affected_server: 'web-01', cpu_exceeded: true },
    }
    const alertOutputData = {
      status: 'completed',
      stderr: '',
      return_code: 0,
      stdout: '{"notification_sent": true, "channel": "#ops-alerts", "message": "web-01 degraded"}\n',
      stdout_json: { notification_sent: true, channel: '#ops-alerts', message: 'web-01 degraded' },
    }

    // Set up execution mock BEFORE saving so the builder's initial execution query
    // hits the mock instead of the real backend (avoids React Query caching empty data)
    let workflowId = 'pending'
    await app.route(/\/api\/v1\/executions/, async (route) => {
      const url = route.request().url()

      if (url.includes('/activities')) {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            resources: [
              {
                id: 'act-gather',
                execution_id: 'e2e-chain-1',
                activity_name: gatherNodeId,
                status: 'completed',
                started_at: '2024-01-01T00:00:01Z',
                completed_at: '2024-01-01T00:00:02Z',
                output_data: gatherOutputData,
                input_data: {},
                error_details: null,
                retry_count: 0,
                iteration: null,
              },
              {
                id: 'act-process',
                execution_id: 'e2e-chain-1',
                activity_name: processNodeId,
                status: 'completed',
                started_at: '2024-01-01T00:00:02Z',
                completed_at: '2024-01-01T00:00:03Z',
                output_data: processOutputData,
                input_data: {},
                error_details: null,
                retry_count: 0,
                iteration: null,
              },
              {
                id: 'act-alert',
                execution_id: 'e2e-chain-1',
                activity_name: alertNodeId,
                status: 'completed',
                started_at: '2024-01-01T00:00:03Z',
                completed_at: '2024-01-01T00:00:04Z',
                output_data: alertOutputData,
                input_data: {},
                error_details: null,
                retry_count: 0,
                iteration: null,
              },
            ],
            next: null,
            prev: null,
          }),
        })
      } else {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            resources: [
              {
                id: 'e2e-chain-1',
                workflow_id: workflowId,
                status: 'completed',
                started_at: '2024-01-01T00:00:00Z',
                completed_at: '2024-01-01T00:00:04Z',
                created_at: '2024-01-01T00:00:00Z',
              },
            ],
            next: null,
            prev: null,
          }),
        })
      }
    })

    // Save the workflow
    await selectProjectIfRequired(app)
    await app.getByPlaceholder('Workflow name').fill(workflowName)
    await app.getByRole('button', { name: 'Save' }).click()
    await expect(app).toHaveURL(/workflow-builder\/(?!new)/, { timeout: 15_000 })
    workflowId = app.url().split('/').pop() ?? workflowId

    // --- Verify each node's output data ---
    // Scope text assertions to the Output panel's SynPanel container using the
    // panelContainer CSS module class (Vite preserves the name in the hashed class).
    const outputPanel = app.locator('[class*="panelContainer"]').filter({
      has: app.getByRole('heading', { name: 'Output', exact: true }),
    })

    // Node 1: Gather Info — output has server diagnostics
    await clickNode(app, 'Gather Info')
    await expect(app.getByLabel('Search json output')).toBeVisible({ timeout: 10_000 })
    await expect(outputPanel.getByText('"stdout_json"')).toBeVisible()
    await expect(outputPanel.getByText('"web-01"')).toBeVisible()
    await expect(outputPanel.getByText('"degraded"')).toBeVisible()

    // Node 2: Process Data — output has alert analysis (different from node 1)
    await closeNodeEditorPanel(app)
    await clickNode(app, 'Process Data')
    await expect(app.getByLabel('Search json output')).toBeVisible({ timeout: 10_000 })
    await expect(outputPanel.getByText('"alert_level"')).toBeVisible()
    await expect(outputPanel.getByText('"warning"')).toBeVisible()
    await expect(outputPanel.getByText('"affected_server"')).toBeVisible()

    // Node 3: Send Alert — output has notification result (different from nodes 1 and 2)
    await closeNodeEditorPanel(app)
    await clickNode(app, 'Send Alert')
    await expect(app.getByLabel('Search json output')).toBeVisible({ timeout: 10_000 })
    await expect(outputPanel.getByText('"notification_sent"')).toBeVisible()
    await expect(outputPanel.getByText('"#ops-alerts"')).toBeVisible()
    await expect(outputPanel.getByText('"web-01 degraded"')).toBeVisible()
  })

  test('input panel shows schema preview at design time without running the workflow', async ({ app }) => {
    // Build: Trigger → Fetch Data (script) → Analyze (script)
    // Clicking "Analyze" should show the schema preview for script output fields
    // because its upstream node (Fetch Data) is a script node with known output schema.
    // No execution data — purely design-time schema discovery.
    await app.goto(toAppUrl('/workflow-builder/new'))
    await selectProjectIfRequired(app)
    await addManualTrigger(app, 'Trigger')
    await addScriptNode(app, 'Fetch Data', 'print("fetching")')
    await addScriptNode(app, 'Analyze', 'print("analyzing")')

    // Click the last node in the chain — its upstream is a script node
    await clickNode(app, 'Analyze')

    // Verify the schema preview appears (not the empty state)
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).toBeVisible({ timeout: 10_000 })

    // The schema preview shows expected output fields for the "script" node type
    // These come from the generated node-output-schemas.ts, not from execution data
    const schemaPreview = app.getByRole('tree', { name: 'Schema preview' })
    await expect(schemaPreview).toBeVisible({ timeout: 10_000 })
    await expect(app.getByText('Expected output fields')).toBeVisible()

    // Verify the key script output fields are listed (type label + field name in grey pill)
    await expect(app.getByText('T stdout', { exact: true })).toBeVisible()
    await expect(app.getByText('T stderr', { exact: true })).toBeVisible()
    await expect(app.getByText('# return_code', { exact: true })).toBeVisible()
    await expect(app.getByText('? stdout_json', { exact: true })).toBeVisible()

    // Output panel should show empty state (no execution data)
    await expect(app.getByText('No output data')).toBeVisible()
  })

  test.skip('input panel transitions from schema preview to real values after execution', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-real-input')

    // Build: Trigger → Fetch Data (script) → Analyze (script)
    await app.goto(toAppUrl('/workflow-builder/new'))
    await selectProjectIfRequired(app)
    await addManualTrigger(app, 'Trigger')
    await addScriptNode(app, 'Fetch Data', 'print("fetching")')
    await addScriptNode(app, 'Analyze', 'print("analyzing")')

    // Extract node IDs while edges are in the store
    await layoutCanvas(app)
    const fetchNode = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Fetch Data' })
    const analyzeNode = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Analyze' })
    await expect(fetchNode).toBeVisible({ timeout: 5_000 })
    const fetchNodeId = await fetchNode.getAttribute('data-id')
    const analyzeNodeId = await analyzeNode.getAttribute('data-id')

    // --- Phase 1: Before execution — schema preview shows field names ---
    await clickNode(app, 'Analyze')
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).toBeVisible({ timeout: 10_000 })
    await expect(app.getByText('Expected output fields')).toBeVisible({ timeout: 10_000 })
    await expect(app.getByText('T stdout', { exact: true })).toBeVisible()
    await expect(app.getByText('# return_code', { exact: true })).toBeVisible()
    await expect(app.getByRole('group', { name: 'Input view selection' })).not.toBeVisible()
    await closeNodeEditorPanel(app)

    // --- Phase 2: Save and run the workflow ---
    await selectProjectIfRequired(app)
    await app.getByPlaceholder('Workflow name').fill(workflowName)
    await app.getByRole('button', { name: 'Save' }).click()
    await expect(app).toHaveURL(/workflow-builder\/(?!new)/, { timeout: 15_000 })
    const builderUrl = app.url()
    const workflowId = builderUrl.split('/').pop()

    // Mock the POST /executions endpoint (run workflow)
    const executionId = 'e2e-run-1'
    await app.route(/\/api\/v1\/executions$/, async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          contentType: 'application/json',
          status: 201,
          body: JSON.stringify({
            id: executionId,
            workflow_id: workflowId,
            status: 'running',
            started_at: '2024-01-01T00:00:00Z',
            created_at: '2024-01-01T00:00:00Z',
          }),
        })
      } else {
        await route.continue()
      }
    })

    // Click Run → confirmation dialog → Run now
    // Since this trigger has no input schema, it runs immediately (no mock data modal)
    await app.getByRole('button', { name: 'Run', exact: true }).click()
    await expect(app.getByRole('button', { name: 'Run now' })).toBeVisible()
    await app.getByRole('button', { name: 'Run now' }).click()

    // After run, user stays in editor — wait for the run dialog to close, confirming execution started
    await expect(app.getByRole('button', { name: 'Run now' })).not.toBeVisible({ timeout: 10_000 })

    // --- Phase 3: Navigate away and mock completed execution data ---
    // Set up execution data mocks BEFORE navigating back
    await app.route(/\/api\/v1\/executions/, async (route) => {
      const url = route.request().url()

      if (url.includes('/activities')) {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            resources: [
              {
                id: 'act-fetch',
                execution_id: executionId,
                activity_name: fetchNodeId,
                status: 'completed',
                started_at: '2024-01-01T00:00:01Z',
                completed_at: '2024-01-01T00:00:02Z',
                output_data: {
                  status: 'completed',
                  return_code: 0,
                  stdout: '{"server": "web-01", "cpu": 92, "healthy": false}\n',
                  stderr: '',
                  stdout_json: { server: 'web-01', cpu: 92, healthy: false },
                },
                input_data: {},
                error_details: null,
                retry_count: 0,
                iteration: null,
              },
              {
                id: 'act-analyze',
                execution_id: executionId,
                activity_name: analyzeNodeId,
                status: 'completed',
                started_at: '2024-01-01T00:00:02Z',
                completed_at: '2024-01-01T00:00:03Z',
                output_data: {
                  status: 'completed',
                  return_code: 0,
                  stdout: '{"alert": "warning"}\n',
                  stderr: '',
                  stdout_json: { alert: 'warning' },
                },
                input_data: {},
                error_details: null,
                retry_count: 0,
                iteration: null,
              },
            ],
            next: null,
            prev: null,
          }),
        })
      } else {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            resources: [
              {
                id: executionId,
                workflow_id: workflowId,
                status: 'completed',
                started_at: '2024-01-01T00:00:00Z',
                completed_at: '2024-01-01T00:00:03Z',
                created_at: '2024-01-01T00:00:00Z',
              },
            ],
            next: null,
            prev: null,
          }),
        })
      }
    })

    // Navigate back to the builder via workflows list (real user flow)
    await app.goto(toAppUrl('/workflows'))
    await app.getByPlaceholder('Filter by name').fill(workflowName)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    await app.getByRole('link', { name: workflowName, exact: true }).click()
    await expect(app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Analyze' })).toBeVisible(
      { timeout: 15_000 }
    )

    // --- Phase 4: Click Analyze node — input should now show REAL values ---
    await clickNode(app, 'Analyze')
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).toBeVisible({ timeout: 10_000 })

    // The view toggle proves real data loaded (schema preview doesn't have it)
    const viewToggle = app.getByRole('group', { name: 'Input view selection' })
    await expect(viewToggle).toBeVisible({ timeout: 10_000 })

    // Real upstream values from Fetch Data's output
    await expect(app.getByText('web-01', { exact: true })).toBeVisible()
    await expect(app.getByText('92', { exact: true })).toBeVisible()

    // Schema preview banner is gone — replaced by actual data
    await expect(app.getByText('Expected output fields')).not.toBeVisible()
  })

  test('input panel sections can be collapsed and expanded', async ({ app }) => {
    // Build: Trigger → Script A → Script B (so Script B has a script upstream with known schema)
    await app.goto(toAppUrl('/workflow-builder/new'))
    await selectProjectIfRequired(app)
    await addManualTrigger(app, 'Trigger')
    await addScriptNode(app, 'Script A', 'print("hello")')
    await addScriptNode(app, 'Script B', 'print("world")')

    await clickNode(app, 'Script B')
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).toBeVisible({ timeout: 10_000 })

    // Schema preview should be visible (upstream node section is expanded by default)
    await expect(app.getByText('Expected output fields')).toBeVisible({ timeout: 10_000 })

    // Collapse the upstream node section via the ExpandableSection toggle
    const nodeToggle = app.getByRole('button', { name: 'Script A', exact: true })
    await nodeToggle.click()
    await expect(app.getByText('Expected output fields')).not.toBeVisible()

    // Expand it again
    await nodeToggle.click()
    await expect(app.getByText('Expected output fields')).toBeVisible()

    // Variables and context section — starts collapsed
    const varsToggle = app.getByRole('button', { name: /Variables and context/i })
    await expect(varsToggle).toBeVisible()
    expect(
      await app
        .getByText('T now')
        .isVisible()
        .catch(() => false)
    ).toBe(false)

    // Expand it
    await varsToggle.click()
    await expect(app.getByText('T now')).toBeVisible()
    await expect(app.getByText('T today')).toBeVisible()

    // Collapse it again
    await varsToggle.click()
    await expect(app.getByText('T now')).not.toBeVisible()
  })

  test.skip('input panel view switching: Schema, Table, and JSON with execution data', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-views')
    await app.goto(toAppUrl('/workflow-builder/new'))
    await selectProjectIfRequired(app)
    await addManualTrigger(app, 'Trigger')
    await addScriptNode(app, 'Fetch', 'print("data")')
    await addScriptNode(app, 'Analyze', 'print("result")')
    await app.getByPlaceholder('Workflow name').fill(workflowName)
    await app.getByRole('button', { name: 'Save' }).click()
    await expect(app).toHaveURL(/workflow-builder\/(?!new)/, { timeout: 15_000 })

    await layoutCanvas(app)
    const workflowId = app.url().split('/').pop()
    const fetchNode = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Fetch' })
    await expect(fetchNode).toBeVisible({ timeout: 5_000 })
    const fetchNodeId = await fetchNode.getAttribute('data-id')
    const analyzeNode = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Analyze' })
    const analyzeNodeId = await analyzeNode.getAttribute('data-id')

    // Mock execution data
    await app.route(/\/api\/v1\/executions/, async (route) => {
      const url = route.request().url()
      if (url.includes('/activities')) {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            resources: [
              {
                id: 'act-fetch',
                execution_id: 'e2e-views-1',
                activity_name: fetchNodeId,
                status: 'completed',
                started_at: '2024-01-01T00:00:01Z',
                completed_at: '2024-01-01T00:00:02Z',
                output_data: { status: 'completed', return_code: 0, stdout: 'data\n', stderr: '' },
                input_data: {},
                error_details: null,
                retry_count: 0,
                iteration: null,
              },
              {
                id: 'act-analyze',
                execution_id: 'e2e-views-1',
                activity_name: analyzeNodeId,
                status: 'completed',
                started_at: '2024-01-01T00:00:02Z',
                completed_at: '2024-01-01T00:00:03Z',
                output_data: { status: 'completed', return_code: 0, stdout: 'result\n', stderr: '' },
                input_data: {},
                error_details: null,
                retry_count: 0,
                iteration: null,
              },
            ],
            next: null,
            prev: null,
          }),
        })
      } else {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            resources: [
              {
                id: 'e2e-views-1',
                workflow_id: workflowId,
                status: 'completed',
                started_at: '2024-01-01T00:00:00Z',
                completed_at: '2024-01-01T00:00:03Z',
                created_at: '2024-01-01T00:00:00Z',
              },
            ],
            next: null,
            prev: null,
          }),
        })
      }
    })

    // Navigate back to builder
    await app.goto(toAppUrl('/workflows'))
    await app.getByPlaceholder('Filter by name').fill(workflowName)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    await app.getByRole('link', { name: workflowName, exact: true }).click()
    await expect(app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Analyze' })).toBeVisible(
      { timeout: 15_000 }
    )

    // Click Analyze node to see Fetch's output as input
    await clickNode(app, 'Analyze')
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).toBeVisible({ timeout: 10_000 })

    // Scope to Input view toggle to avoid ambiguity with Output view toggle
    const inputToggle = app.getByRole('group', { name: 'Input view selection' })
    await expect(inputToggle).toBeVisible({ timeout: 10_000 })

    // Schema view (default) — shows type labels for upstream node data
    await expect(inputToggle.getByRole('button', { name: 'Schema', pressed: true })).toBeVisible()
    await expect(app.getByText('T stdout')).toBeVisible()

    // Switch to Table view
    await inputToggle.getByRole('button', { name: 'Table' }).click()
    await expect(inputToggle.getByRole('button', { name: 'Table', pressed: true })).toBeVisible()
    await expect(app.getByRole('columnheader', { name: 'status' })).toBeVisible()

    // Switch to JSON view
    await inputToggle.getByRole('button', { name: 'JSON' }).click()
    await expect(inputToggle.getByRole('button', { name: 'JSON', pressed: true })).toBeVisible()
    const jsonInput = app.getByRole('region', { name: 'JSON input' })
    await expect(jsonInput).toContainText('"status"')

    // Switch back to Schema
    await inputToggle.getByRole('button', { name: 'Schema' }).click()
    await expect(inputToggle.getByRole('button', { name: 'Schema', pressed: true })).toBeVisible()
    await expect(app.getByText('T status')).toBeVisible()
  })

  test.skip('input panel expandable sections switch between upstream nodes', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-selector')
    await app.goto(toAppUrl('/workflow-builder/new'))
    await selectProjectIfRequired(app)
    await addManualTrigger(app, 'Trigger')
    await addScriptNode(app, 'Step A', 'print("alpha")')
    await addScriptNode(app, 'Step B', 'print("beta")')
    await addScriptNode(app, 'Step C', 'print("gamma")')
    await app.getByPlaceholder('Workflow name').fill(workflowName)
    await app.getByRole('button', { name: 'Save' }).click()
    await expect(app).toHaveURL(/workflow-builder\/(?!new)/, { timeout: 15_000 })

    await layoutCanvas(app)
    const workflowId = app.url().split('/').pop()

    const stepANode = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Step A' })
    const stepBNode = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Step B' })
    const stepCNode = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Step C' })
    await expect(stepANode).toBeVisible({ timeout: 5_000 })
    const stepAId = await stepANode.getAttribute('data-id')
    const stepBId = await stepBNode.getAttribute('data-id')
    const stepCId = await stepCNode.getAttribute('data-id')

    // Mock execution data for all nodes
    await app.route(/\/api\/v1\/executions/, async (route) => {
      const url = route.request().url()
      if (url.includes('/activities')) {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            resources: [
              {
                id: 'act-a',
                execution_id: 'e2e-sel-1',
                activity_name: stepAId,
                status: 'completed',
                started_at: '2024-01-01T00:00:01Z',
                completed_at: '2024-01-01T00:00:02Z',
                output_data: { status: 'completed', return_code: 0, stdout: 'alpha\n', stderr: '' },
                input_data: {},
                error_details: null,
                retry_count: 0,
                iteration: null,
              },
              {
                id: 'act-b',
                execution_id: 'e2e-sel-1',
                activity_name: stepBId,
                status: 'completed',
                started_at: '2024-01-01T00:00:02Z',
                completed_at: '2024-01-01T00:00:03Z',
                output_data: { status: 'completed', return_code: 0, stdout: 'beta\n', stderr: '' },
                input_data: {},
                error_details: null,
                retry_count: 0,
                iteration: null,
              },
              {
                id: 'act-c',
                execution_id: 'e2e-sel-1',
                activity_name: stepCId,
                status: 'completed',
                started_at: '2024-01-01T00:00:03Z',
                completed_at: '2024-01-01T00:00:04Z',
                output_data: { status: 'completed', return_code: 0, stdout: 'gamma\n', stderr: '' },
                input_data: {},
                error_details: null,
                retry_count: 0,
                iteration: null,
              },
            ],
            next: null,
            prev: null,
          }),
        })
      } else {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            resources: [
              {
                id: 'e2e-sel-1',
                workflow_id: workflowId,
                status: 'completed',
                started_at: '2024-01-01T00:00:00Z',
                completed_at: '2024-01-01T00:00:04Z',
                created_at: '2024-01-01T00:00:00Z',
              },
            ],
            next: null,
            prev: null,
          }),
        })
      }
    })

    // Navigate back to builder
    await app.goto(toAppUrl('/workflows'))
    await app.getByPlaceholder('Filter by name').fill(workflowName)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    await app.getByRole('link', { name: workflowName, exact: true }).click()
    await expect(app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Step C' })).toBeVisible({
      timeout: 15_000,
    })

    // Click Step C — it has Step B, Step A, and Trigger as upstream ancestors
    await clickNode(app, 'Step C')
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).toBeVisible({ timeout: 10_000 })

    // View toggle should be visible (execution data exists)
    await expect(app.getByRole('button', { name: 'Schema', pressed: true })).toBeVisible({ timeout: 10_000 })

    // Each upstream node has its own ExpandableSection — Step B is expanded by default (closest upstream)
    const stepBToggle = app.getByRole('button', { name: 'Step B', exact: true })
    await expect(stepBToggle).toBeVisible({ timeout: 10_000 })
    await expect(app.getByText('beta')).toBeVisible()

    // Expand Step A section to see its data
    const stepAToggle = app.getByRole('button', { name: 'Step A', exact: true })
    await expect(stepAToggle).toBeVisible()
    await stepAToggle.click()
    await expect(app.getByText('alpha')).toBeVisible()
  })

  test.skip('output panel view switching: Schema, Table, and JSON with execution data', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-out-views')
    const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Run script')
    await openWorkflowInBuilder(app, workflowName, id)

    // Extract node ID and workflow ID
    await layoutCanvas(app)
    const scriptNode = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Run script' })
    await expect(scriptNode).toBeVisible({ timeout: 5_000 })
    const scriptNodeId = await scriptNode.getAttribute('data-id')
    const workflowId = app.url().split('/').pop()

    // Register route mocks BEFORE navigating back to the builder,
    // so execution data requests are intercepted on page load.
    await app.route(/\/api\/v1\/executions/, async (route) => {
      const url = route.request().url()
      if (url.includes('/activities')) {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            resources: [
              {
                id: 'act-out-views',
                execution_id: 'e2e-out-views-1',
                activity_name: scriptNodeId,
                status: 'completed',
                started_at: '2024-01-01T00:00:01Z',
                completed_at: '2024-01-01T00:00:02Z',
                output_data: {
                  status: 'completed',
                  return_code: 0,
                  stdout: '{"server": "web-01"}\n',
                  stderr: '',
                  stdout_json: { server: 'web-01' },
                },
                input_data: {},
                error_details: null,
                retry_count: 0,
                iteration: null,
              },
            ],
            next: null,
            prev: null,
          }),
        })
      } else {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            resources: [
              {
                id: 'e2e-out-views-1',
                workflow_id: workflowId,
                status: 'completed',
                started_at: '2024-01-01T00:00:00Z',
                completed_at: '2024-01-01T00:00:02Z',
                created_at: '2024-01-01T00:00:00Z',
              },
            ],
            next: null,
            prev: null,
          }),
        })
      }
    })

    // Navigate back to builder so mocks are active
    await app.goto(toAppUrl('/workflows'))
    await app.getByPlaceholder('Filter by name').fill(workflowName)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    await app.getByRole('link', { name: workflowName, exact: true }).click()
    await expect(
      app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Run script' })
    ).toBeVisible({ timeout: 15_000 })

    // Click the script node to open the editor
    await clickNode(app, 'Run script')
    await expect(app.getByRole('heading', { name: 'Output', exact: true })).toBeVisible({ timeout: 10_000 })

    // Scope to Output view toggle to avoid ambiguity with Input view toggle
    const outputToggle = app.getByRole('group', { name: 'Output view selection' })
    await expect(outputToggle).toBeVisible({ timeout: 10_000 })

    // JSON view is the default
    await expect(outputToggle.getByRole('button', { name: 'JSON', pressed: true })).toBeVisible()
    await expect(app.getByText('"stdout_json"')).toBeVisible()

    // Switch to Schema view — tree with type labels
    await outputToggle.getByRole('button', { name: 'Schema' }).click()
    await expect(outputToggle.getByRole('button', { name: 'Schema', pressed: true })).toBeVisible()
    const schemaTree = app.getByRole('tree', { name: 'Output schema' })
    await expect(schemaTree).toBeVisible()

    // Switch to Table view — grid with column headers
    await outputToggle.getByRole('button', { name: 'Table' }).click()
    await expect(outputToggle.getByRole('button', { name: 'Table', pressed: true })).toBeVisible()
    await expect(app.getByRole('grid', { name: 'Output data' })).toBeVisible()
    await expect(app.getByRole('columnheader', { name: 'status' })).toBeVisible()

    // Switch back to JSON view
    await outputToggle.getByRole('button', { name: 'JSON' }).click()
    await expect(outputToggle.getByRole('button', { name: 'JSON', pressed: true })).toBeVisible()
    await expect(app.getByText('"stdout_json"')).toBeVisible()
  })

  test('run step button is inline with tabs', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-run-btn')
    const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Run script')
    await openWorkflowInBuilder(app, workflowName, id)

    await clickNode(app, 'Run script')

    const parametersTab = app.getByRole('tab', { name: 'Parameters' })
    const runStepButton = app.getByRole('button', { name: 'Run step' })

    await expect(parametersTab).toBeVisible({ timeout: 15_000 })
    await expect(runStepButton).toBeVisible({ timeout: 15_000 })

    const flexContainer = app.locator('.pf-v6-l-flex').filter({
      has: app.getByRole('tab', { name: 'Parameters' }),
    })
    await expect(flexContainer.getByRole('button', { name: 'Run step' })).toBeVisible()
  })

  test('mock data pin flow in Input panel', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-mock-pin')
    await app.goto(toAppUrl('/workflow-builder/new'))
    await selectProjectIfRequired(app)

    await app.getByRole('button', { name: 'Manual trigger' }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Trigger')
    await app.getByRole('button', { name: 'Create' }).click()

    let panel = await clickAddConnectedStep(app)
    await panel.getByRole('button', { name: 'Action', exact: true }).click()
    await panel.getByRole('button', { name: 'Script', exact: true }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Script A')
    await fillCodeEditor(app, { value: 'print("alpha")' })
    await app.getByRole('button', { name: 'Create' }).click()

    panel = await clickAddConnectedStep(app)
    await panel.getByRole('button', { name: 'Action', exact: true }).click()
    await panel.getByRole('button', { name: 'Script', exact: true }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Script B')
    await fillCodeEditor(app, { value: 'print("beta")' })
    await app.getByRole('button', { name: 'Create' }).click()
    await closeNodeEditorPanel(app)

    await selectProjectIfRequired(app)
    await app.getByPlaceholder('Workflow name').fill(workflowName)
    await app.getByRole('button', { name: 'Save' }).click()
    await expect(app).toHaveURL(/workflow-builder\/(?!new)/, { timeout: 15_000 })

    await clickNode(app, 'Script B')
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).toBeVisible({ timeout: 15_000 })

    const inputPanel = app.locator('[class*="panelContainer"]').filter({
      has: app.getByRole('heading', { name: 'Input', exact: true }),
    })
    const setMockButton = inputPanel.locator('[data-ouia-component-type="PF6/MenuToggle"]').filter({
      hasText: 'Set mock data',
    })
    await expect(setMockButton).toBeVisible()
    await setMockButton.click()

    await clickMenuItemWhenVisible(app, 'Script A')

    await expect(app.getByText('Editing mock data for:')).toBeVisible()
    await expect(app.getByRole('button', { name: 'Pin data', exact: true })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Cancel', exact: true })).toBeVisible()

    await app.getByRole('button', { name: 'Pin data', exact: true }).click()

    await expect(app.getByText('Mock data pinned (1)')).toBeVisible()
    await expect(
      inputPanel.locator('[data-ouia-component-type="PF6/MenuToggle"]').filter({
        hasText: 'Unpin data',
      })
    ).toBeVisible()
  })

  test('mock data unpin flow', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-mock-unpin')
    await app.goto(toAppUrl('/workflow-builder/new'))
    await selectProjectIfRequired(app)

    await app.getByRole('button', { name: 'Manual trigger' }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Trigger')
    await app.getByRole('button', { name: 'Create' }).click()

    let panel = await clickAddConnectedStep(app)
    await panel.getByRole('button', { name: 'Action', exact: true }).click()
    await panel.getByRole('button', { name: 'Script', exact: true }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Script A')
    await fillCodeEditor(app, { value: 'print("alpha")' })
    await app.getByRole('button', { name: 'Create' }).click()

    panel = await clickAddConnectedStep(app)
    await panel.getByRole('button', { name: 'Action', exact: true }).click()
    await panel.getByRole('button', { name: 'Script', exact: true }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Script B')
    await fillCodeEditor(app, { value: 'print("beta")' })
    await app.getByRole('button', { name: 'Create' }).click()
    await closeNodeEditorPanel(app)

    await selectProjectIfRequired(app)
    await app.getByPlaceholder('Workflow name').fill(workflowName)
    await app.getByRole('button', { name: 'Save' }).click()
    await expect(app).toHaveURL(/workflow-builder\/(?!new)/, { timeout: 15_000 })

    await clickNode(app, 'Script B')
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).toBeVisible({ timeout: 15_000 })

    const inputPanel = app.locator('[class*="panelContainer"]').filter({
      has: app.getByRole('heading', { name: 'Input', exact: true }),
    })
    const setMockButton = inputPanel.locator('[data-ouia-component-type="PF6/MenuToggle"]').filter({
      hasText: 'Set mock data',
    })
    await expect(setMockButton).toBeVisible({ timeout: 10_000 })
    await setMockButton.click()
    await clickMenuItemWhenVisible(app, 'Script A')
    await app.getByRole('button', { name: 'Pin data', exact: true }).click()
    await expect(app.getByText('Mock data pinned (1)')).toBeVisible()

    const unpinButton = inputPanel.locator('[data-ouia-component-type="PF6/MenuToggle"]').filter({
      hasText: 'Unpin data',
    })
    await unpinButton.click()
    await clickMenuItemWhenVisible(app, 'Script A')

    await expect(app.getByText('Mock data pinned (1)')).not.toBeVisible()
  })

  test('mock data cancel flow', { tag: ['@konflux-skip'] }, async ({ app }) => {
    const workflowName = buildUniqueName('e2e-mock-cancel')
    await app.goto(toAppUrl('/workflow-builder/new'))
    await selectProjectIfRequired(app)

    await app.getByRole('button', { name: 'Manual trigger' }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Trigger')
    await app.getByRole('button', { name: 'Create' }).click()

    let panel = await clickAddConnectedStep(app)
    await panel.getByRole('button', { name: 'Action', exact: true }).click()
    await panel.getByRole('button', { name: 'Script', exact: true }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Script A')
    await fillCodeEditor(app, { value: 'print("alpha")' })
    await app.getByRole('button', { name: 'Create' }).click()

    panel = await clickAddConnectedStep(app)
    await panel.getByRole('button', { name: 'Action', exact: true }).click()
    await panel.getByRole('button', { name: 'Script', exact: true }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Script B')
    await fillCodeEditor(app, { value: 'print("beta")' })
    await app.getByRole('button', { name: 'Create' }).click()
    await closeNodeEditorPanel(app)

    await selectProjectIfRequired(app)
    await app.getByPlaceholder('Workflow name').fill(workflowName)
    await app.getByRole('button', { name: 'Save' }).click()
    await expect(app).toHaveURL(/workflow-builder\/(?!new)/, { timeout: 15_000 })

    await clickNode(app, 'Script B')
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).toBeVisible({ timeout: 10_000 })

    const inputPanel = app.locator('[class*="panelContainer"]').filter({
      has: app.getByRole('heading', { name: 'Input', exact: true }),
    })
    const setMockButton = inputPanel.locator('[data-ouia-component-type="PF6/MenuToggle"]').filter({
      hasText: 'Set mock data',
    })
    await expect(setMockButton).toBeVisible()
    await setMockButton.click()
    await clickMenuItemWhenVisible(app, 'Script A')
    await expect(app.getByRole('button', { name: 'Pin data', exact: true })).toBeVisible()

    await app.getByRole('button', { name: 'Cancel', exact: true }).click()

    await expect(app.getByRole('button', { name: 'Pin data' })).not.toBeVisible()
    await expect(app.getByText(/Mock data pinned/)).not.toBeVisible()
  })

  test('schema preview shows expected output fields in predecessor section', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-test-alert')
    await app.goto(toAppUrl('/workflow-builder/new'))
    await selectProjectIfRequired(app)

    await app.getByRole('button', { name: 'Manual trigger' }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Trigger')
    await app.getByRole('button', { name: 'Create' }).click()

    let panel = await clickAddConnectedStep(app)
    await panel.getByRole('button', { name: 'Action', exact: true }).click()
    await panel.getByRole('button', { name: 'Script', exact: true }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Script A')
    await fillCodeEditor(app, { value: 'print("test")' })
    await app.getByRole('button', { name: 'Create' }).click()

    panel = await clickAddConnectedStep(app)
    await panel.getByRole('button', { name: 'Action', exact: true }).click()
    await panel.getByRole('button', { name: 'Script', exact: true }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Script B')
    await fillCodeEditor(app, { value: 'print("test2")' })
    await app.getByRole('button', { name: 'Create' }).click()
    await closeNodeEditorPanel(app)

    await selectProjectIfRequired(app)
    await app.getByPlaceholder('Workflow name').fill(workflowName)
    await app.getByRole('button', { name: 'Save' }).click()
    await expect(app).toHaveURL(/workflow-builder\/(?!new)/, { timeout: 15_000 })

    await clickNode(app, 'Script B')
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).toBeVisible({ timeout: 10_000 })

    await expect(app.getByText('Expected output fields')).toBeVisible({ timeout: 10_000 })

    const schemaPreview = app.getByRole('tree', { name: 'Schema preview' })
    await expect(schemaPreview).toBeVisible()
  })

  test('output panel "Set mock data" opens and closes editor', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-out-mock')
    const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Run script')
    await openWorkflowInBuilder(app, workflowName, id)

    await clickNode(app, 'Run script')
    await expect(app.getByRole('heading', { name: 'Output', exact: true })).toBeVisible({ timeout: 10_000 })

    const setMockButtons = app.getByRole('button', { name: 'Set mock data' })
    const setMockButton = setMockButtons.last()
    await expect(setMockButton).toBeVisible()
    await setMockButton.click()

    await expect(app.getByRole('button', { name: 'Pin data', exact: true })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Cancel', exact: true })).toBeVisible()

    await app.getByRole('button', { name: 'Cancel', exact: true }).click()
    await expect(app.getByRole('button', { name: 'Pin data', exact: true })).not.toBeVisible()
  })

  test('pinned data persists across node editor reopens', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-mock-persist')
    await app.goto(toAppUrl('/workflow-builder/new'))
    await selectProjectIfRequired(app)

    await app.getByRole('button', { name: 'Manual trigger' }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Trigger')
    await app.getByRole('button', { name: 'Create' }).click()

    let panel = await clickAddConnectedStep(app)
    await panel.getByRole('button', { name: 'Action', exact: true }).click()
    await panel.getByRole('button', { name: 'Script', exact: true }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Script A')
    await fillCodeEditor(app, { value: 'print("alpha")' })
    await app.getByRole('button', { name: 'Create' }).click()

    panel = await clickAddConnectedStep(app)
    await panel.getByRole('button', { name: 'Action', exact: true }).click()
    await panel.getByRole('button', { name: 'Script', exact: true }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Script B')
    await fillCodeEditor(app, { value: 'print("beta")' })
    await app.getByRole('button', { name: 'Create' }).click()
    await closeNodeEditorPanel(app)

    await selectProjectIfRequired(app)
    await app.getByPlaceholder('Workflow name').fill(workflowName)
    await app.getByRole('button', { name: 'Save' }).click()
    await expect(app).toHaveURL(/workflow-builder\/(?!new)/, { timeout: 15_000 })

    await clickNode(app, 'Script B')
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).toBeVisible({ timeout: 10_000 })

    const inputPanel = app.locator('[class*="panelContainer"]').filter({
      has: app.getByRole('heading', { name: 'Input', exact: true }),
    })
    const setMockButton = inputPanel.locator('[data-ouia-component-type="PF6/MenuToggle"]').filter({
      hasText: 'Set mock data',
    })
    await setMockButton.click()
    await clickMenuItemWhenVisible(app, 'Script A')
    await app.getByRole('button', { name: 'Pin data', exact: true }).click()
    await expect(app.getByText('Mock data pinned (1)')).toBeVisible()

    await closeNodeEditorPanel(app)
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).not.toBeVisible()

    await clickNode(app, 'Script B')
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).toBeVisible({ timeout: 10_000 })

    await expect(app.getByText('Mock data pinned (1)')).toBeVisible()
  })

  test('clicking the copy button on an Input panel field announces the expression was copied', async ({ app }) => {
    await app.goto(toAppUrl('/workflow-builder/new'))
    await selectProjectIfRequired(app)
    await addManualTrigger(app, 'Trigger')
    await addScriptNode(app, 'Script A', 'print("hello")')
    await addScriptNode(app, 'Script B', 'print("world")')

    await clickNode(app, 'Script B')
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).toBeVisible({ timeout: 10_000 })
    await expect(app.getByText('Expected output fields')).toBeVisible({ timeout: 10_000 })

    const stdoutLabel = app.getByText('T stdout', { exact: true })
    await expect(stdoutLabel).toBeVisible()
    await stdoutLabel.hover()

    // Each tree leaf renders a copy button; the aria-label includes the field path,
    // anchored to closing } to avoid matching stdout_json.
    const copyButton = app.getByRole('button', { name: /Copy expression.*\.stdout\}/ })
    await expect(copyButton).toBeVisible()
    await copyButton.click()

    // Each tree item has its own live region — scope to avoid strict mode violation
    // from the 5 sibling role="status" elements.
    await expect(app.getByRole('treeitem', { name: /T stdout/ }).getByRole('status')).toContainText(
      'Expression copied to clipboard'
    )
  })

  test.skip('dragging a field from the Input panel inserts the expression into a Parameters form field', async ({
    app,
  }) => {
    await app.goto(toAppUrl('/workflow-builder/new'))
    await selectProjectIfRequired(app)
    await addManualTrigger(app, 'Trigger')
    await addScriptNode(app, 'Script A', 'print("hello")')
    await addAgenticNode(app, 'Agent B', 'initial-prompt')

    // clickNode reopens the editor after addAgenticNode closes it
    await clickNode(app, 'Agent B')
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).toBeVisible({ timeout: 10_000 })
    await expect(app.getByText('Expected output fields')).toBeVisible({ timeout: 10_000 })

    // Scope to the tree to avoid ambiguity with other draggable elements
    const stdoutLeaf = app
      .getByRole('tree', { name: 'Schema preview' })
      .locator('[draggable="true"]')
      .filter({ hasText: 'T stdout' })
    await expect(stdoutLeaf).toBeVisible()

    const promptField = app.getByRole('textbox', { name: 'Prompt', exact: true })
    await expect(promptField).toBeVisible()

    await stdoutLeaf.dragTo(promptField)

    // Drop handler appends the expression: "initial-prompt${<nodeId>.stdout}"
    await expect(promptField).toHaveValue(/initial-prompt\$\{[^}]+\.stdout\}/)
  })
})

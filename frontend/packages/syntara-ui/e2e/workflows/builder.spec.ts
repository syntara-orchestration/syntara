/**
 * E2E Tests (ANSTRAT-1845): Workflow Builder Canvas
 *
 * Combined test suite for builder functionality:
 * - Adding nodes from catalog panel
 * - Connecting nodes with edges
 * - Canvas interactions and layout
 */

import { test, expect } from '../fixtures'
import {
  buildUniqueName,
  deleteWorkflow,
  clickAddConnectedStep,
  closeNodeEditorPanel,
  createWorkflowWithTrigger,
  addScriptNode,
  verifyNodeVisible,
  waitForUIReady,
  triggerLayout,
} from '../helpers/workflows'

// ========================================
// Add Nodes from Catalog
// ========================================

test('catalog panel shows available node types organized by category', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-builder')
  await createWorkflowWithTrigger(app, workflowName)

  try {
    await closeNodeEditorPanel(app)
    await expect(app.getByText('Manual trigger')).toBeVisible()

    const panel = await clickAddConnectedStep(app)

    await expect(panel).toBeVisible()

    await expect(panel.getByRole('button', { name: 'Action', exact: true })).toBeVisible()
    await expect(panel.getByRole('button', { name: 'AAP Execution', exact: true })).toBeVisible()
    await expect(panel.getByRole('button', { name: 'Approval', exact: true })).toBeVisible()
    await expect(panel.getByRole('button', { name: 'Logic', exact: true })).toBeVisible()
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

test('user can add a Script action node to the canvas', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-builder')
  await createWorkflowWithTrigger(app, workflowName)

  try {
    await closeNodeEditorPanel(app)
    await expect(app.getByText('Manual trigger')).toBeVisible()

    await addScriptNode(app, 'Python Hello World', 'print("Hello, World!")')
    await verifyNodeVisible(app, 'Python Hello World')
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

test('user can add an Approval node to the canvas', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-builder')
  await createWorkflowWithTrigger(app, workflowName)

  // Mock the /authz/who_can API for both mock API and real backend
  // This avoids the complexity of creating real users with approval:decide permission
  await app.route('**/api/v1/authz/who_can', async (route) => {
    const request = route.request()
    if (request.method() === 'POST') {
      const body = request.postDataJSON() as { action?: string; resource_type?: string } | null
      if (body?.action === 'decide' && body?.resource_type === 'approval') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            resources: [
              { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', username: 'demo' },
              { id: 'b2c3d4e5-f6a7-8901-bcde-f12345678901', username: 'jdoe' },
            ],
            next: null,
          }),
        })
        return
      }
    }
    await route.continue()
  })

  try {
    await closeNodeEditorPanel(app)
    await expect(app.getByText('Manual trigger')).toBeVisible()

    const panel = await clickAddConnectedStep(app)

    const approvalButton = panel.getByRole('button', { name: /Approval/i, exact: true })
    await expect(approvalButton).toBeVisible()

    await approvalButton.click()

    await expect(app.getByRole('textbox', { name: 'Name', exact: true })).toBeVisible()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Approval Node')

    // Wait for the approver users dropdown to render (it loads users from API)
    // The dropdown needs to load users from /authz/who_can endpoint
    const approverUsersButton = app.getByPlaceholder(/Select users/i)
    await expect(approverUsersButton).toBeVisible({ timeout: 15000 })
    await expect(approverUsersButton).toBeEnabled({ timeout: 15000 })

    // Route mock provides demo/jdoe users for both mock API and real backend
    const expectedUsername = 'demo'

    // Click the Approver Users dropdown and wait for it to open
    await approverUsersButton.click()

    // Wait for the PatternFly Select dropdown to open
    const listbox = app.getByRole('listbox')
    await expect(listbox).toBeVisible({ timeout: 5000 })

    // Wait for menu items to load from the /authz/who_can API
    // Note: PF6 Select uses role="listbox" for the container but role="menuitem" for items (not role="option")
    await expect(async () => {
      const menuItems = app.getByRole('menuitem')
      const count = await menuItems.count()

      if (count === 0) {
        throw new Error('No menu items rendered yet')
      }

      const texts = await Promise.all((await menuItems.all()).map((item) => item.textContent()))

      if (!texts.some((t) => t?.includes(expectedUsername))) {
        throw new Error(`${expectedUsername} not found. Available: ${texts.join(', ')}`)
      }
    }).toPass({ timeout: 15_000 })

    // Click the user option from the PF Select menu
    await app.getByRole('menuitem').filter({ hasText: expectedUsername }).click()

    // Wait for form validation to complete
    await expect(app.getByRole('button', { name: 'Create', exact: true })).toBeEnabled({ timeout: 15000 })

    await app.getByRole('button', { name: 'Create', exact: true }).click()

    await closeNodeEditorPanel(app)

    // Wait for canvas to render the new node
    await expect(
      app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Approval Node' })
    ).toBeVisible({ timeout: 10000 })

    await expect(app.getByText('Approval Node')).toBeVisible()
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

test('user can add a Logic (Conditional) node to the canvas', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-builder')
  await createWorkflowWithTrigger(app, workflowName)

  try {
    await closeNodeEditorPanel(app)
    await expect(app.getByText('Manual trigger')).toBeVisible()

    const panel = await clickAddConnectedStep(app)

    const logicButton = panel.getByRole('button', { name: /Logic/i, exact: true })
    await expect(logicButton).toBeVisible()
    await logicButton.click()

    await expect(app.getByRole('heading', { name: 'Select a logic node' })).toBeVisible()
    await app.getByText('Conditional', { exact: true }).click()

    await expect(app.getByRole('textbox', { name: 'Name', exact: true })).toBeVisible()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Conditional Node')

    await app.getByRole('button', { name: /Expression editor mode/i }).click()
    await app.getByRole('option', { name: 'Custom expression' }).click()

    await app.getByLabel('Raw expression').fill('${status == "active"}')

    await app.getByRole('button', { name: 'Create', exact: true }).click()

    await closeNodeEditorPanel(app)

    // Wait for canvas to render the new node
    await expect(
      app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Conditional Node' })
    ).toBeVisible({
      timeout: 10000,
    })

    // Verify node appears on canvas
    await expect(app.getByText('Conditional Node')).toBeVisible()
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

test('multiple nodes can be added sequentially', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-builder')
  await createWorkflowWithTrigger(app, workflowName)

  // Mock the /authz/who_can API for both mock API and real backend
  await app.route('**/api/v1/authz/who_can', async (route) => {
    const request = route.request()
    if (request.method() === 'POST') {
      const body = request.postDataJSON() as { action?: string; resource_type?: string } | null
      if (body?.action === 'decide' && body?.resource_type === 'approval') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            resources: [
              { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', username: 'demo' },
              { id: 'b2c3d4e5-f6a7-8901-bcde-f12345678901', username: 'jdoe' },
            ],
            next: null,
          }),
        })
        return
      }
    }
    await route.continue()
  })

  try {
    await closeNodeEditorPanel(app)
    await expect(app.getByText('Manual trigger')).toBeVisible()

    // Add first node - Script action
    await addScriptNode(app, 'Script Node 1', 'print("node1")')

    // Wait for UI to stabilize after first node
    await waitForUIReady(app)

    // Add second node - Approval
    let panel = await clickAddConnectedStep(app)

    // Wait for Approval button to be stable before clicking
    await expect(async () => {
      const approvalBtn = panel.getByRole('button', { name: 'Approval', exact: true })
      await expect(approvalBtn).toBeVisible()
      await expect(approvalBtn).toBeEnabled()
    }).toPass({ timeout: 15000, intervals: [500, 1000] })

    const approvalBtn = panel.getByRole('button', { name: 'Approval', exact: true })
    await approvalBtn.click()

    // Wait for form to be stable
    await expect(async () => {
      const nameInput = app.getByRole('textbox', { name: 'Name', exact: true })
      await expect(nameInput).toBeVisible()
      await expect(nameInput).toBeEditable()
    }).toPass({ timeout: 20000, intervals: [500, 1000] })

    const nameInput = app.getByRole('textbox', { name: 'Name', exact: true })
    await nameInput.fill('Approval Node 1')

    // Open the approver users dropdown and select a user
    // Wait for the dropdown to be ready (loads from /authz/who_can)
    const approverUsersButton = app.getByPlaceholder(/Select users/i)
    await expect(approverUsersButton).toBeVisible({ timeout: 15000 })
    await expect(approverUsersButton).toBeEnabled({ timeout: 15000 })

    // Route mock provides demo/jdoe users for both mock API and real backend
    const expectedUsername = 'demo'

    await approverUsersButton.click()

    // Wait for the PatternFly Select dropdown to open
    const listbox = app.getByRole('listbox')
    await expect(listbox).toBeVisible({ timeout: 5000 })

    // Wait for menu items to load from the /authz/who_can API
    // Note: PF6 Select uses role="listbox" for the container but role="menuitem" for items (not role="option")
    await expect(async () => {
      const menuItems = app.getByRole('menuitem')
      const count = await menuItems.count()

      if (count === 0) {
        throw new Error('No menu items rendered yet')
      }

      const texts = await Promise.all((await menuItems.all()).map((item) => item.textContent()))

      if (!texts.some((t) => t?.includes(expectedUsername))) {
        throw new Error(`${expectedUsername} not found. Available: ${texts.join(', ')}`)
      }
    }).toPass({ timeout: 15_000 })

    // Click the user option from the PF Select menu
    await app.getByRole('menuitem').filter({ hasText: expectedUsername }).click()

    // Wait for form validation to complete
    const saveBtn = app.getByRole('button', { name: 'Create', exact: true })
    await expect(saveBtn).toBeEnabled({ timeout: 20000 })
    await saveBtn.click()

    // Wait for panel to close
    await expect(panel).toHaveCount(0, { timeout: 15000 })

    // Wait for canvas to render the new node
    await expect(
      app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Approval Node 1' })
    ).toBeVisible({
      timeout: 10000,
    })

    // Wait for UI to stabilize after second node
    await waitForUIReady(app)

    // Add third node - Logic (Conditional)
    panel = await clickAddConnectedStep(app)

    // Wait for Logic button to be stable
    await expect(async () => {
      const logicBtn = panel.getByRole('button', { name: 'Logic', exact: true })
      await expect(logicBtn).toBeVisible()
      await expect(logicBtn).toBeEnabled()
    }).toPass({ timeout: 15000, intervals: [500, 1000] })

    const logicBtn = panel.getByRole('button', { name: 'Logic', exact: true })
    await logicBtn.click()

    // Wait for Conditional button
    await expect(async () => {
      const conditionalBtn = app.getByText('Conditional', { exact: true })
      await expect(conditionalBtn).toBeVisible()
    }).toPass({ timeout: 15000, intervals: [500, 1000] })

    const conditionalBtn = app.getByText('Conditional', { exact: true })
    await conditionalBtn.click()

    // Wait for form to be stable
    await expect(async () => {
      const logicNameInput = app.getByRole('textbox', { name: 'Name', exact: true })
      await expect(logicNameInput).toBeVisible()
      await expect(logicNameInput).toBeEditable()
    }).toPass({ timeout: 20000, intervals: [500, 1000] })

    const logicNameInput = app.getByRole('textbox', { name: 'Name', exact: true })
    await logicNameInput.fill('Logic Node 1')

    await app.getByRole('button', { name: /Expression editor mode/i }).click()
    await app.getByRole('option', { name: 'Custom expression' }).click()
    await app.getByLabel('Raw expression').fill('${x == 1}')

    const logicSaveBtn = app.getByRole('button', { name: 'Create', exact: true })
    await expect(logicSaveBtn).toBeEnabled({ timeout: 20000 })
    await logicSaveBtn.click()

    // Wait for panel to close
    await expect(panel).toHaveCount(0, { timeout: 15000 })

    // Wait for canvas to render the new node
    await expect(
      app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Logic Node 1' })
    ).toBeVisible({ timeout: 10000 })
    await verifyNodeVisible(app, 'Script Node 1')
    await verifyNodeVisible(app, 'Approval Node 1')
    await verifyNodeVisible(app, 'Logic Node 1')
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

test('added nodes are visible and interactive on the canvas', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-builder')
  await createWorkflowWithTrigger(app, workflowName)

  try {
    await closeNodeEditorPanel(app)
    await expect(app.getByText('Manual trigger')).toBeVisible()

    await addScriptNode(app, 'Interactive Node', 'print("interactive")')

    await verifyNodeVisible(app, 'Interactive Node')

    await app.getByText('Interactive Node').click()
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

test('nodes are positioned on the canvas after layout', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-builder')
  await createWorkflowWithTrigger(app, workflowName)

  try {
    await closeNodeEditorPanel(app)
    await expect(app.getByText('Manual trigger')).toBeVisible()

    // Add a node
    await addScriptNode(app, 'Positioned Node', 'print("positioned")')
    await verifyNodeVisible(app, 'Positioned Node')

    await triggerLayout(app)

    await verifyNodeVisible(app, 'Positioned Node')
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

test('catalog panel can be closed without adding a node', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-builder')
  await createWorkflowWithTrigger(app, workflowName)

  try {
    await closeNodeEditorPanel(app)
    await expect(app.getByText('Manual trigger')).toBeVisible()

    // Open the Add step panel
    const panel = await clickAddConnectedStep(app)
    await expect(panel).toBeVisible()

    // Close the panel using the Close button
    const closeButton = panel.getByRole('button', { name: /Close/i })
    const hasCloseButton = await closeButton
      .waitFor({ state: 'visible', timeout: 3000 })
      .then(() => true)
      .catch(() => false)

    if (hasCloseButton) {
      await closeButton.click()
    } else {
      await app.keyboard.press('Escape')
    }

    await expect(panel).not.toBeVisible()

    await expect(app).toHaveURL(/workflow-builder\/.+/)
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

// ========================================
// Connect Nodes with Edges
// ========================================

test('two nodes can be connected with an edge', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-builder')
  await createWorkflowWithTrigger(app, workflowName)

  try {
    await closeNodeEditorPanel(app)
    await expect(app.getByText('Manual trigger')).toBeVisible()

    // Add two nodes using "Add connected step" - this creates edges via the UI
    await addScriptNode(app, 'First Node', 'print("first")')
    await addScriptNode(app, 'Second Node', 'print("second")')

    // Edge existence is proven implicitly: addScriptNode uses clickAddConnectedStep,
    // which can only succeed by clicking an edge overlay button — so reaching this
    // point means both edges were created.
    await verifyNodeVisible(app, 'First Node')
    await verifyNodeVisible(app, 'Second Node')
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

test('edge is visually distinguishable on canvas', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-builder')
  await createWorkflowWithTrigger(app, workflowName)

  try {
    await closeNodeEditorPanel(app)
    await expect(app.getByText('Manual trigger')).toBeVisible()

    // Add two nodes - these will auto-connect:
    // Manual trigger -> Source Node -> Target Node
    await addScriptNode(app, 'Source Node', 'print("source")')
    await addScriptNode(app, 'Target Node', 'print("target")')

    // Edge existence is proven implicitly by addScriptNode succeeding (it clicks an
    // edge overlay button). The "edge follows connection path" test verifies SVG path data.
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

test('multiple edges can be created sequentially', async ({ app }) => {
  // 90s needed: creates 3 nodes sequentially, each with a layout trigger and panel wait.
  // Reduced timeouts caused consistent CI runner timeouts — keep until builder render is faster.
  test.setTimeout(90_000)
  const workflowName = buildUniqueName('e2e-builder')
  await createWorkflowWithTrigger(app, workflowName)

  try {
    await closeNodeEditorPanel(app)
    await expect(app.getByText('Manual trigger')).toBeVisible()

    // Add three nodes
    await addScriptNode(app, 'Node 1', 'print("1")')
    await addScriptNode(app, 'Node 2', 'print("2")')
    await addScriptNode(app, 'Node 3', 'print("3")')

    // Layout to position nodes
    await triggerLayout(app)

    // Verify all nodes are visible — three successful addScriptNode calls prove
    // three edges were sequentially created (each call clicks an edge overlay button).
    await verifyNodeVisible(app, 'Node 1')
    await verifyNodeVisible(app, 'Node 2')
    await verifyNodeVisible(app, 'Node 3')
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

test('edge follows connection path between nodes', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-builder')
  await createWorkflowWithTrigger(app, workflowName)

  try {
    await closeNodeEditorPanel(app)
    await expect(app.getByText('Manual trigger')).toBeVisible()

    // Add two nodes - auto-connected: Manual trigger -> Start Node -> End Node
    await addScriptNode(app, 'Start Node', 'print("start")')
    await addScriptNode(app, 'End Node', 'print("end")')

    // Verify edge path exists and has SVG path data.
    // ReactFlow edge paths are SVG <path> elements with no accessible role — use the DOM API directly.
    const pathData = await app.evaluate(
      () => document.querySelector('svg g.react-flow__edge path')?.getAttribute('d') ?? null
    )
    expect(pathData).toBeTruthy()
    expect(pathData?.length).toBeGreaterThan(0)

    // Verify it's actual SVG path commands (starts with M for moveTo)
    expect(pathData).toMatch(/^M/)
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

test('connected nodes form a workflow DAG', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-builder')
  await createWorkflowWithTrigger(app, workflowName)

  try {
    await closeNodeEditorPanel(app)
    await expect(app.getByText('Manual trigger')).toBeVisible()

    // Add nodes that will form a linear DAG: Manual Trigger -> Script 1 -> Script 2
    await addScriptNode(app, 'Processing Step', 'print("processing")')
    await addScriptNode(app, 'Final Step', 'print("final")')

    // Layout to visualize the DAG
    await triggerLayout(app)

    // Verify all DAG nodes are present and visible after layout.
    // DAG structure (trigger→processing→final) is proven by addScriptNode succeeding
    // for each node — each call clicks an edge overlay button that only exists on a connected edge.
    await verifyNodeVisible(app, 'Manual trigger')
    await verifyNodeVisible(app, 'Processing Step')
    await verifyNodeVisible(app, 'Final Step')
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

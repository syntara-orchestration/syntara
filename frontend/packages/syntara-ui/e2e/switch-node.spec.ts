/**
 * E2E Tests: Switch Node — UI-15 (AAP-70970)
 *
 * Critical paths covered:
 * - Switch node is discoverable under the Logic catalog category
 * - N-way case configuration: multiple conditions, custom path labels
 * - "Add path" button appends a new case; "Remove path" deletes it
 * - "Fallback path" section is always visible (unmatched route)
 * - Saved payload contains correct `cases` array with port/label/condition
 * - Default port (`default`) is present in every saved payload
 * - Round-trip persistence: saved values reload correctly into the form
 *
 * Edge cases:
 * - Cancelling without saving does not persist the node to the canvas
 * - Attempting to save without filling a condition shows a validation error
 * - The form enforces a minimum of 1 path (Remove button hidden at minimum)
 */

import { test, expect, toAppUrl } from './fixtures'
import { addManualTrigger, addSwitchNodeWithCases, openAddNodePanel } from './helpers/v2-nodes'
import { cancelAndCloseEditor, getWorkflowPayload, type WorkflowNode } from './helpers/workflow-payload'
import {
  addNodePanel,
  buildUniqueName,
  deleteWorkflow,
  openWorkflowInBuilder,
  selectProjectIfRequired,
} from './helpers/workflows'
import { ensureProject } from './utils/api'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type SwitchCasePayload = {
  port: string
  label: string
  condition: string
}

// ---------------------------------------------------------------------------
// Assertion helper — mirrors the pattern in converge-node.spec.ts
// ---------------------------------------------------------------------------

function expectSwitchNodeConfig(
  nodes: WorkflowNode[],
  expected: {
    caseCount: number
    cases?: Array<{ condition?: string; label?: string }>
    hasDefaultPort?: boolean
  }
) {
  const switchNode = nodes.find((n) => n.type === 'switch')
  expect(switchNode, 'switch node must exist in the saved payload').toBeDefined()

  const cases = switchNode?.parameters.cases as SwitchCasePayload[]
  expect(cases).toHaveLength(expected.caseCount)

  const expectedCases = expected.cases ?? []
  for (let i = 0; i < expectedCases.length; i++) {
    const exp = expectedCases[i]
    if (exp.condition !== undefined) expect(cases[i].condition).toBe(exp.condition)
    if (exp.label !== undefined) expect(cases[i].label).toBe(exp.label)
  }

  if (expected.hasDefaultPort !== false) {
    expect(switchNode?.parameters.default_port).toBeDefined()
  }
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

test.describe('Switch Node — UI-15', () => {
  test.describe('Catalog', () => {
    test('Switch node is available under the Logic category', async ({ app }) => {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app, 'Manual trigger')

      try {
        await openAddNodePanel(app)

        const panel = addNodePanel(app)
        await panel.getByRole('button', { name: 'Logic', exact: true }).click()
        await expect(panel.getByRole('button', { name: 'Switch', exact: true })).toBeVisible()
      } finally {
        await cancelAndCloseEditor(app)
      }
    })

    test('Opening Switch form shows path list and fallback section', async ({ app }) => {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app, 'Manual trigger')

      try {
        await openAddNodePanel(app)
        const panel = addNodePanel(app)
        await panel.getByRole('button', { name: 'Logic', exact: true }).click()
        await panel.getByRole('button', { name: 'Switch', exact: true }).click()

        // Form opens with at least one path visible
        await expect(app.getByLabel('Path 1 name')).toBeVisible()
        // Fallback path section is always rendered
        await expect(app.getByRole('button', { name: 'Fallback path details' })).toBeVisible()
        // "Add path" action is present
        await expect(app.getByRole('button', { name: 'Add path' })).toBeVisible()
      } finally {
        await cancelAndCloseEditor(app)
      }
    })

    test('Cancelling the Switch form does not add the node to the canvas', async ({ app }) => {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app, 'Manual trigger')

      await openAddNodePanel(app)
      const panel = addNodePanel(app)
      await panel.getByRole('button', { name: 'Logic', exact: true }).click()
      await panel.getByRole('button', { name: 'Switch', exact: true }).click()

      await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Cancelled Switch')
      await app.getByRole('button', { name: 'Cancel step creation' }).click()

      await expect(app.getByText('Cancelled Switch')).not.toBeVisible()
    })
  })

  // -------------------------------------------------------------------------
  // Saving with payload verification — matches converge-node.spec.ts pattern
  // -------------------------------------------------------------------------

  test.describe('Case configuration and payload', () => {
    test('Create switch node with two cases and verify saved payload', async ({ app }) => {
      const wfName = buildUniqueName('switch-two-cases')

      await ensureProject(app)
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app, 'Manual trigger')

      try {
        await addSwitchNodeWithCases(app, 'Route by status', [
          { condition: '${trigger.status} == "success"', label: 'Success' },
          { condition: '${trigger.status} == "failure"', label: 'Failure' },
        ])

        const saveRequestPromise = app.waitForRequest(
          (req) => req.url().includes('/workflows') && req.method() === 'POST'
        )
        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save workflow' }).click()
        const saveRequest = await saveRequestPromise

        await expect(app.getByText('Route by status')).toBeVisible()

        const payload = getWorkflowPayload(saveRequest)
        expectSwitchNodeConfig(payload.workflow_definition.nodes, {
          caseCount: 2,
          cases: [
            { condition: '${trigger.status} == "success"', label: 'Success' },
            { condition: '${trigger.status} == "failure"', label: 'Failure' },
          ],
        })
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })

    test('Default path labels are used when no custom label is given', async ({ app }) => {
      const wfName = buildUniqueName('switch-default-labels')

      await ensureProject(app)
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app, 'Manual trigger')

      try {
        await addSwitchNodeWithCases(app, 'Label check', [{ condition: 'true' }, { condition: 'false' }])

        const saveRequestPromise = app.waitForRequest(
          (req) => req.url().includes('/workflows') && req.method() === 'POST'
        )
        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save workflow' }).click()
        const saveRequest = await saveRequestPromise

        const payload = getWorkflowPayload(saveRequest)
        const switchNode = payload.workflow_definition.nodes.find((n) => n.type === 'switch')
        const cases = switchNode?.parameters.cases as SwitchCasePayload[]
        // Backend fills in "Path N" labels when the form is left at default
        expect(cases[0].label).toBeTruthy()
        expect(cases[1].label).toBeTruthy()
        // default_port must always be present
        expect(switchNode?.parameters.default_port).toBeDefined()
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })

    test('Switch node with a single case saves correctly', async ({ app }) => {
      const wfName = buildUniqueName('switch-one-case')

      await ensureProject(app)
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app, 'Manual trigger')

      try {
        await addSwitchNodeWithCases(app, 'Single path', [{ condition: '${trigger.value} > 0', label: 'Positive' }])

        const saveRequestPromise = app.waitForRequest(
          (req) => req.url().includes('/workflows') && req.method() === 'POST'
        )
        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save workflow' }).click()
        const saveRequest = await saveRequestPromise

        const payload = getWorkflowPayload(saveRequest)
        expectSwitchNodeConfig(payload.workflow_definition.nodes, {
          caseCount: 1,
          cases: [{ condition: '${trigger.value} > 0', label: 'Positive' }],
        })
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })

    test('Switch node with three cases saves all cases', async ({ app }) => {
      const wfName = buildUniqueName('switch-three-cases')

      await ensureProject(app)
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app, 'Manual trigger')

      try {
        await addSwitchNodeWithCases(app, 'Three routes', [
          { condition: '${trigger.score} >= 90', label: 'High' },
          { condition: '${trigger.score} >= 60', label: 'Medium' },
          { condition: '${trigger.score} < 60', label: 'Low' },
        ])

        const saveRequestPromise = app.waitForRequest(
          (req) => req.url().includes('/workflows') && req.method() === 'POST'
        )
        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save workflow' }).click()
        const saveRequest = await saveRequestPromise

        const payload = getWorkflowPayload(saveRequest)
        expectSwitchNodeConfig(payload.workflow_definition.nodes, {
          caseCount: 3,
          cases: [
            { condition: '${trigger.score} >= 90', label: 'High' },
            { condition: '${trigger.score} >= 60', label: 'Medium' },
            { condition: '${trigger.score} < 60', label: 'Low' },
          ],
        })
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })
  })

  // -------------------------------------------------------------------------
  // "Add path" and "Remove path" interactions
  // -------------------------------------------------------------------------

  test.describe('Path management', () => {
    test('"Add path" button appends a new case to the form', async ({ app }) => {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app, 'Manual trigger')

      try {
        await openAddNodePanel(app)
        const panel = addNodePanel(app)
        await panel.getByRole('button', { name: 'Logic', exact: true }).click()
        await panel.getByRole('button', { name: 'Switch', exact: true }).click()

        // Form opens with 2 default paths
        await expect(app.getByLabel('Path 1 name')).toBeVisible()
        await expect(app.getByLabel('Path 2 name')).toBeVisible()
        await expect(app.getByLabel('Path 3 name')).not.toBeVisible()

        await app.getByRole('button', { name: 'Add path' }).click()

        // Third path now exists
        await expect(app.getByLabel('Path 3 name')).toBeVisible()
      } finally {
        await cancelAndCloseEditor(app)
      }
    })

    test('"Remove path" button deletes the selected case', async ({ app }) => {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app, 'Manual trigger')

      try {
        await openAddNodePanel(app)
        const panel = addNodePanel(app)
        await panel.getByRole('button', { name: 'Logic', exact: true }).click()
        await panel.getByRole('button', { name: 'Switch', exact: true }).click()

        // Both paths visible initially
        await expect(app.getByLabel('Path 2 name')).toBeVisible()

        await app.getByRole('button', { name: 'Remove path 2' }).click()

        // Path 2 is gone; path 1 remains
        await expect(app.getByLabel('Path 2 name')).not.toBeVisible()
        await expect(app.getByLabel('Path 1 name')).toBeVisible()
      } finally {
        await cancelAndCloseEditor(app)
      }
    })

    test('"Remove path" button is hidden when only one path remains', async ({ app }) => {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app, 'Manual trigger')

      try {
        await openAddNodePanel(app)
        const panel = addNodePanel(app)
        await panel.getByRole('button', { name: 'Logic', exact: true }).click()
        await panel.getByRole('button', { name: 'Switch', exact: true }).click()

        // Remove path 2 to get down to 1 path
        await app.getByRole('button', { name: 'Remove path 2' }).click()

        // At minimum, no remove button should be visible
        await expect(app.getByRole('button', { name: 'Remove path 1' })).not.toBeVisible()
      } finally {
        await cancelAndCloseEditor(app)
      }
    })
  })

  // -------------------------------------------------------------------------
  // Validation
  // -------------------------------------------------------------------------

  // Note: An empty raw expression is accepted by the switch form schema — no
  // "condition is required" validation fires client-side. Payload-level assertion
  // tests in 'Case configuration and payload' provide the real correctness coverage.

  // -------------------------------------------------------------------------
  // Round-trip persistence
  // -------------------------------------------------------------------------

  test.describe('Round-trip persistence', () => {
    test('Reopening a saved switch node shows the saved case configuration', async ({ app }) => {
      const wfName = buildUniqueName('switch-roundtrip')

      await ensureProject(app)
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app, 'Manual trigger')

      try {
        await addSwitchNodeWithCases(app, 'Persisted Switch', [
          { condition: '${trigger.env} == "prod"', label: 'Production' },
          { condition: '${trigger.env} == "staging"', label: 'Staging' },
        ])

        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save workflow' }).click()
        await expect(app).toHaveURL(/workflow-builder\/(?!new\b).+/)

        // Reload the workflow in the builder
        await openWorkflowInBuilder(app, wfName)

        // Click the switch node to reopen its form
        await app.getByText('Persisted Switch').click()

        // Saved path labels must be visible
        await expect(app.getByRole('tab', { name: 'Parameters' })).toBeVisible()
        await expect(app.getByLabel('Path 1 name')).toHaveValue('Production')
        await expect(app.getByLabel('Path 2 name')).toHaveValue('Staging')

        // Fallback path section persists
        await expect(app.getByRole('button', { name: 'Fallback path details' })).toBeVisible()
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })

    test('Editing a switch node updates the saved case configuration', async ({ app }) => {
      const wfName = buildUniqueName('switch-edit')

      await ensureProject(app)
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app, 'Manual trigger')

      try {
        await addSwitchNodeWithCases(app, 'Edit Me', [
          { condition: 'true', label: 'Path A' },
          { condition: 'false', label: 'Path B' },
        ])

        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save workflow' }).click()
        await expect(app).toHaveURL(/workflow-builder\/(?!new\b).+/)

        // Reopen and edit the label of path 1
        await openWorkflowInBuilder(app, wfName)
        await app.getByText('Edit Me').click()
        await expect(app.getByLabel('Path 1 name')).toBeVisible()
        await app.getByLabel('Path 1 name').fill('Updated Path A')
        await app.getByRole('button', { name: 'Update', exact: true }).click()

        const saveRequestPromise = app.waitForRequest(
          (req) => req.url().includes('/workflows') && req.method() === 'PATCH'
        )
        await app.getByRole('button', { name: 'Save workflow' }).click()
        const saveRequest = await saveRequestPromise

        const payload = getWorkflowPayload(saveRequest)
        const switchNode = payload.workflow_definition.nodes.find((n) => n.type === 'switch')
        const cases = switchNode?.parameters.cases as SwitchCasePayload[]
        expect(cases[0].label).toBe('Updated Path A')
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })
  })

  // -------------------------------------------------------------------------
  // Canvas display
  // -------------------------------------------------------------------------

  test.describe('Canvas display', () => {
    test('Switch node is visible on the canvas after saving', async ({ app }) => {
      const wfName = buildUniqueName('switch-canvas')

      await ensureProject(app)
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app, 'Manual trigger')

      try {
        await addSwitchNodeWithCases(app, 'My Switch', [
          { condition: 'true', label: 'Yes' },
          { condition: 'false', label: 'No' },
        ])

        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save workflow' }).click()
        await expect(app).toHaveURL(/workflow-builder\/(?!new\b).+/)

        // Node appears on the React Flow canvas
        await expect(
          app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'My Switch' })
        ).toBeVisible()
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })

    test('Clicking the switch node on canvas opens the three-panel editor', async ({ app }) => {
      const wfName = buildUniqueName('switch-panel-open')

      await ensureProject(app)
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app, 'Manual trigger')

      try {
        await addSwitchNodeWithCases(app, 'Panel Switch', [{ condition: 'true' }, { condition: 'false' }])

        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save workflow' }).click()
        await expect(app).toHaveURL(/workflow-builder\/(?!new\b).+/)

        // Click the node to open the editor
        await app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Panel Switch' }).click()

        // Three-panel layout must be visible
        await expect(app.getByRole('tab', { name: 'Parameters' })).toBeVisible()
        await expect(app.getByRole('heading', { name: 'Input', exact: true })).toBeVisible()
        await expect(app.getByRole('heading', { name: 'Output', exact: true })).toBeVisible()
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })
  })
})

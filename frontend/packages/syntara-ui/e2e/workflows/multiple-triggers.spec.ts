/**
 * E2E Tests (UI-22): Workflow Builder — Choose Trigger When Multiple Exist
 *
 * Objective: Verify the Run button shows a trigger selection dropdown when a workflow
 * has more than one trigger, and that selecting a trigger opens the run confirmation dialog.
 *
 * Test coverage:
 * - Single trigger: Run renders as a plain button (not a dropdown)
 * - Multiple triggers: Run renders as a dropdown listing all trigger names
 * - Selecting a trigger from the dropdown opens the run confirmation dialog
 * - Triggers without a name fall back to "Trigger N" label
 */

import { test, expect } from '../fixtures'
import { buildUniqueName, openBuilderById } from '../helpers/workflows'
import { createWorkflowViaApi, deleteWorkflowViaApi } from '../utils/api'

const TRIGGER_NAME = 'Manual trigger'
const SECONDARY_TRIGGER_NAME = 'Secondary trigger'

test.describe('Multiple triggers', () => {
  test('shows Run button (not dropdown) when workflow has a single trigger', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-single-trigger')
    const { id: workflowId } = await createWorkflowViaApi({
      app,
      name: workflowName,
      triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: TRIGGER_NAME, parameters: {} }],
    })
    try {
      await openBuilderById(app, workflowId)
      await expect(app.getByText(TRIGGER_NAME)).toBeVisible({ timeout: 30_000 })
      // Single trigger: Run renders as a plain button
      await expect(app.getByRole('button', { name: 'Run' })).toBeVisible()
      // Dropdown toggle only appears when multiple triggers exist
      await expect(app.getByRole('button', { name: 'Run workflow' })).not.toBeVisible()
    } finally {
      await deleteWorkflowViaApi(app, workflowId)
    }
  })

  test('shows Run dropdown listing all trigger names when workflow has multiple triggers', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-multi-trigger')
    const { id: workflowId } = await createWorkflowViaApi({
      app,
      name: workflowName,
      triggers: [
        { id: 'trigger_1', type: 'manual_trigger', name: TRIGGER_NAME, parameters: {} },
        { id: 'trigger_2', type: 'manual_trigger', name: SECONDARY_TRIGGER_NAME, parameters: {} },
      ],
    })
    try {
      await openBuilderById(app, workflowId)
      await expect(app.getByText(TRIGGER_NAME)).toBeVisible({ timeout: 30_000 })
      // Multiple triggers: Run becomes a MenuToggle (aria-label="Run workflow") instead of a plain button
      const runToggle = app.getByRole('button', { name: 'Run workflow' })
      await expect(runToggle).toBeVisible()
      await runToggle.click()
      await expect(app.getByRole('menuitem', { name: TRIGGER_NAME })).toBeVisible()
      await expect(app.getByRole('menuitem', { name: SECONDARY_TRIGGER_NAME })).toBeVisible()
    } finally {
      await deleteWorkflowViaApi(app, workflowId)
    }
  })

  test('selecting a trigger from the Run dropdown opens the run confirmation dialog', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-trigger-select')
    const { id: workflowId } = await createWorkflowViaApi({
      app,
      name: workflowName,
      triggers: [
        { id: 'trigger_1', type: 'manual_trigger', name: TRIGGER_NAME, parameters: {} },
        { id: 'trigger_2', type: 'manual_trigger', name: SECONDARY_TRIGGER_NAME, parameters: {} },
      ],
    })
    try {
      await openBuilderById(app, workflowId)
      await expect(app.getByText(TRIGGER_NAME)).toBeVisible({ timeout: 30_000 })
      await app.getByRole('button', { name: 'Run workflow' }).click()
      await app.getByRole('menuitem', { name: TRIGGER_NAME }).click()
      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()
      // Dialog title confirms the correct workflow is being run
      await expect(dialog.getByRole('heading', { name: new RegExp(`Run ${workflowName}`) })).toBeVisible()
      await dialog.getByRole('button', { name: 'Cancel' }).click()
      await expect(dialog).not.toBeVisible()
    } finally {
      await deleteWorkflowViaApi(app, workflowId)
    }
  })

  test('shows "Trigger N" fallback name for triggers without an explicit name', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-fallback-name')
    const { id: workflowId } = await createWorkflowViaApi({
      app,
      name: workflowName,
      triggers: [
        { id: 'trigger_1', type: 'manual_trigger', name: TRIGGER_NAME, parameters: {} },
        { id: 'trigger_2', type: 'manual_trigger', parameters: {} }, // no name — falls back to "Trigger 2"
      ],
    })
    try {
      await openBuilderById(app, workflowId)
      await expect(app.getByText(TRIGGER_NAME)).toBeVisible({ timeout: 30_000 })
      await app.getByRole('button', { name: 'Run workflow' }).click()
      // trigger.name ?? `Trigger ${index + 1}` — unnamed trigger at index 1 becomes "Trigger 2"
      await expect(app.getByRole('menuitem', { name: TRIGGER_NAME })).toBeVisible()
      await expect(app.getByRole('menuitem', { name: 'Trigger 2' })).toBeVisible()
    } finally {
      await deleteWorkflowViaApi(app, workflowId)
    }
  })
})

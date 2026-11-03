/**
 * E2E Tests: Workflow Builder - Delete Steps and Edges
 *
 * Objective: Verify that steps and edges can be deleted from the canvas.
 *
 * Test coverage:
 * - Delete a middle step and verify connected edges are removed
 * - Delete first/last steps in a sequence and verify remaining steps stay on canvas
 */

import { test, expect } from '../fixtures'
import {
  buildUniqueName,
  deleteWorkflow,
  closeStepEditorPanel,
  createWorkflowWithTrigger,
  addScriptStep,
  verifyStepVisible,
  triggerLayout,
} from '../helpers/workflows'

test('delete a middle step removes the step and its connected edges', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-delete')
  await createWorkflowWithTrigger(app, workflowName)

  try {
    await closeStepEditorPanel(app)
    await expect(app.getByText('Manual trigger')).toBeVisible()

    // Add three connected steps: Manual trigger → Step A → Step B → Step C
    await addScriptStep(app, 'Step A', 'print("A")')
    await addScriptStep(app, 'Step B', 'print("B")')
    await addScriptStep(app, 'Step C', 'print("C")')

    // Layout to position steps
    await triggerLayout(app)

    // Verify all steps are visible
    await verifyStepVisible(app, 'Manual trigger')
    await verifyStepVisible(app, 'Step A')
    await verifyStepVisible(app, 'Step B')
    await verifyStepVisible(app, 'Step C')

    // ReactFlow edges have no ARIA role — CSS is the only way to count them.
    // count() is a snapshot so wrap in toPass() to retry until the DOM settles.
    const edges = app.locator('svg g.react-flow__edge')
    let initialEdgeCount = 0
    await expect(async () => {
      initialEdgeCount = await edges.count()
      expect(initialEdgeCount).toBeGreaterThanOrEqual(3)
    }).toPass()

    // Delete Step B using its kebab menu
    const nodeB = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Step B' })
    await expect(nodeB).toBeVisible()

    // Hover first so the step is settled before interacting with it
    await nodeB.hover()
    const kebabButton = nodeB.getByLabel('Step actions menu')
    await expect(kebabButton).toBeVisible()
    await kebabButton.click()

    // Click Delete in the dropdown menu
    const deleteMenuItem = app.getByRole('menuitem', { name: 'Delete' })
    await expect(deleteMenuItem).toBeVisible()
    await deleteMenuItem.click()

    // Verify Step B is removed from canvas
    await expect(nodeB).not.toBeAttached()

    // Verify edges connected to Step B are removed.
    await expect(async () => {
      const finalEdgeCount = await edges.count()
      expect(finalEdgeCount).toBeLessThan(initialEdgeCount)
    }).toPass()

    // Verify Step A and Step C remain on the canvas
    await verifyStepVisible(app, 'Manual trigger')
    await verifyStepVisible(app, 'Step A')
    await verifyStepVisible(app, 'Step C')
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

const deletePositionCases = [
  {
    position: 'first',
    steps: ['First', 'Second', 'Third'],
    deleteStep: 'First',
    remainingSteps: ['Second', 'Third'],
  },
  {
    position: 'last',
    steps: ['Start', 'Middle', 'End'],
    deleteStep: 'End',
    remainingSteps: ['Start', 'Middle'],
  },
]

for (const { position, steps, deleteStep, remainingSteps } of deletePositionCases) {
  test(`delete ${position} step in a sequence keeps other steps`, async ({ app }) => {
    const workflowName = buildUniqueName('e2e-delete')
    await createWorkflowWithTrigger(app, workflowName)

    try {
      await closeStepEditorPanel(app)
      await expect(app.getByText('Manual trigger')).toBeVisible()

      // Add steps
      for (const stepName of steps) {
        await addScriptStep(app, stepName, `print("${stepName}")`)
      }

      await triggerLayout(app)

      // Verify all steps visible
      for (const stepName of steps) {
        await verifyStepVisible(app, stepName)
      }

      // Delete the specified step using kebab menu
      const targetNode = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: deleteStep })
      await expect(targetNode).toBeVisible()

      // Hover first so the step is settled before interacting with it
      await targetNode.hover()
      const kebabButton = targetNode.getByLabel('Step actions menu')
      await expect(kebabButton).toBeVisible()
      await kebabButton.click()

      await app.getByRole('menuitem', { name: 'Delete' }).click()

      // Verify deleted step is removed from the DOM
      await expect(targetNode).not.toBeAttached({ timeout: 10000 })

      // Verify remaining steps are still visible
      await verifyStepVisible(app, 'Manual trigger')
      for (const stepName of remainingSteps) {
        await verifyStepVisible(app, stepName)
      }
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })
}

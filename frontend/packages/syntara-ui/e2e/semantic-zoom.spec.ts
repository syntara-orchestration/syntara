/**
 * A large imported workflow must remain usable when adding a step and crossing
 * the semantic-zoom threshold.
 */
import type { V2WorkflowDefinition } from '@syntara/contracts'

import { test, expect } from './fixtures'
import { buildUniqueName, clickAddConnectedStep, fillCodeEditor, startWorkflowWithTrigger } from './helpers/workflows'

const IMPORTED_STEP_COUNT = 60

function createLargeWorkflowDefinition(name: string): V2WorkflowDefinition {
  return {
    schema_version: '2.0.0',
    name,
    description: 'Large workflow for semantic-zoom regression coverage',
    triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
    nodes: Array.from({ length: IMPORTED_STEP_COUNT }, (_, index) => ({
      id: `node_${index + 1}`,
      type: 'script',
      name: `Imported step ${index + 1}`,
      parameters: { language: 'python', code: `print(${index + 1})` },
    })),
    edges: Array.from({ length: IMPORTED_STEP_COUNT }, (_, index) => ({
      from: index === 0 ? 'trigger_1' : `node_${index}`,
      to: `node_${index + 1}`,
    })),
  }
}

test('large workflow remains usable across semantic zoom after adding a step', async ({ app }) => {
  test.slow()

  const pageErrors: Error[] = []
  app.on('pageerror', (error) => pageErrors.push(error))

  await startWorkflowWithTrigger(app)

  const workflowName = buildUniqueName('e2e-semantic-zoom')
  const fileChooserPromise = app.waitForEvent('filechooser')
  await app.getByRole('button', { name: 'Workflow actions' }).click()
  await app.getByRole('menuitem', { name: 'Import workflow' }).click()
  const fileChooser = await fileChooserPromise
  await fileChooser.setFiles({
    name: `${workflowName}.json`,
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(createLargeWorkflowDefinition(workflowName))),
  })

  // Assert on the terminal node — a failed import would otherwise let the next step
  // silently attach to the original trigger. React Flow may not render text at this
  // zoom level with many nodes, so assert by role rather than visible text.
  const terminalImportedStep = app
    .locator('.react-flow')
    .getByRole('button', { name: `Imported step ${IMPORTED_STEP_COUNT}` })
  await expect(terminalImportedStep, 'the imported 60-step workflow should be on the canvas').toBeAttached({
    timeout: 15_000,
  })

  const panel = await clickAddConnectedStep(app)
  await panel.getByRole('button', { name: 'Action', exact: true }).click()
  await panel.getByRole('button', { name: 'Script', exact: true }).click()
  await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Step added after import')
  await fillCodeEditor(app, { value: 'print("added")' })
  await app.getByRole('button', { name: 'Create', exact: true }).click()
  await expect(app.getByRole('button', { name: 'Create', exact: true })).not.toBeAttached({ timeout: 15_000 })

  // SynStepSemanticZoomBody collapses nodes to a single tooltip button at this zoom level;
  // past the threshold they render a full card with a heading instead — hence the two locators below.
  const addedStepSemanticZoomButton = app
    .locator('.react-flow')
    .getByRole('button', { name: 'Step added after import, Script' })
  const addedStepHeading = app.locator('.react-flow').getByRole('heading', { name: 'Step added after import' })
  await expect(addedStepSemanticZoomButton, 'the large imported workflow should start in semantic zoom').toBeVisible()

  const zoomIn = app.getByRole('button', { name: 'Zoom in' })
  for (let index = 0; index < 15 && pageErrors.length === 0; index += 1) {
    await zoomIn.click()
  }

  expect(
    pageErrors.map((error) => error.message),
    'Zooming a large workflow must not trigger an uncaught React error'
  ).toEqual([])
  await expect(zoomIn).toBeVisible()
  await expect(addedStepHeading, 'zooming in should have crossed the semantic-zoom threshold').toBeVisible()
})

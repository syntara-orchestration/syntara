/**
 * E2E Tests: Loop Node Configuration [UI-16]
 *
 * Covers Loop (While) and Loop (For Each) node configuration:
 * - Adding and configuring loop nodes
 * - Custom item/index variables
 * - Max iterations
 * - Loop type switching
 * - Child node connections for loop body
 * - Configuration persistence across saves and edits
 */

import { test, expect } from '../fixtures'
import { openAddStepPanel, selectCategoryAndStepType } from '../helpers/v2-steps'
import {
  addChildScriptToLoopStep,
  addForEachLoopStep,
  addWhileLoopStep,
  configureLoopStep,
  saveAndCloseStepForm,
} from '../helpers/v2-steps-loop'
import {
  buildUniqueName,
  closeStepEditorPanel,
  deleteWorkflow,
  openStepForEditing,
  openWorkflowInBuilder,
  saveWorkflow,
  startWorkflowWithTrigger,
  triggerLayout,
  verifyStepVisible,
  waitForUIReady,
} from '../helpers/workflows'

test.describe('Loop Node Configuration [UI-16]', () => {
  test('adds Loop (While) node with condition', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-loop-while')

    try {
      await startWorkflowWithTrigger(app)

      await addWhileLoopStep(app, {
        name: 'While loop',
        condition: '${counter} < 10',
      })

      await verifyStepVisible(app, 'While loop')
      await saveWorkflow(app, workflowName)

      await expect(app.getByPlaceholder('Workflow name')).toHaveValue(workflowName)
      await verifyStepVisible(app, 'While loop')
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('adds Loop (For Each) node with items expression', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-loop-foreach')

    try {
      await startWorkflowWithTrigger(app)

      await addForEachLoopStep(app, {
        name: 'For each loop',
        items: '${trigger.items}',
      })

      await verifyStepVisible(app, 'For each loop')
      await saveWorkflow(app, workflowName)

      await expect(app.getByPlaceholder('Workflow name')).toHaveValue(workflowName)
      await verifyStepVisible(app, 'For each loop')
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('verifies custom item and index variables persist', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-loop-foreach-vars')

    try {
      await startWorkflowWithTrigger(app)

      await addForEachLoopStep(app, {
        name: 'Process items',
        items: '${input.records}',
        itemVariable: 'record',
        indexVariable: 'recordIndex',
      })

      await verifyStepVisible(app, 'Process items')
      await saveWorkflow(app, workflowName)

      await openStepForEditing(app, 'Process items')

      await expect(app.getByRole('textbox', { name: 'Name', exact: true })).toHaveValue('Process items')
      await expect(app.getByRole('button', { name: 'Type', exact: true })).toContainText('For each')
      await expect(app.getByRole('textbox', { name: 'Items expression', exact: true })).toHaveValue('${input.records}')
      await expect(app.getByRole('textbox', { name: 'Item variable', exact: true })).toHaveValue('record')
      await expect(app.getByRole('textbox', { name: 'Index variable', exact: true })).toHaveValue('recordIndex')

      await closeStepEditorPanel(app)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('verifies max iterations persist on Loop (While)', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-loop-while-maxiter')

    try {
      await startWorkflowWithTrigger(app)

      await addWhileLoopStep(app, {
        name: 'Limited while loop',
        condition: 'true',
        maxIterations: 100,
      })

      await verifyStepVisible(app, 'Limited while loop')
      await saveWorkflow(app, workflowName)

      await openStepForEditing(app, 'Limited while loop')

      await expect(app.getByRole('textbox', { name: 'Name', exact: true })).toHaveValue('Limited while loop')
      await expect(app.getByRole('button', { name: 'Type', exact: true })).toContainText('While')
      await expect(app.getByLabel(/Raw expression/i)).toHaveValue('true')
      await expect(app.getByRole('spinbutton', { name: /Max iterations/i })).toHaveValue('100')

      await closeStepEditorPanel(app)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('verifies loop type switch from While to For Each persists', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-loop-type-switch')

    try {
      await startWorkflowWithTrigger(app)

      await openAddStepPanel(app)
      await selectCategoryAndStepType(app, 'Logic', 'Loop')
      await configureLoopStep(app, {
        name: 'Switchable loop',
        type: 'while',
        condition: 'true',
      })
      await saveAndCloseStepForm(app)

      await verifyStepVisible(app, 'Switchable loop')

      await openStepForEditing(app, 'Switchable loop')
      await configureLoopStep(app, {
        type: 'forEach',
        items: '${input.data}',
      })
      await saveAndCloseStepForm(app)

      await saveWorkflow(app, workflowName)

      await openStepForEditing(app, 'Switchable loop')

      await expect(app.getByRole('button', { name: 'Type', exact: true })).toContainText('For each')
      await expect(app.getByRole('textbox', { name: 'Items expression', exact: true })).toHaveValue('${input.data}')
      await expect(app.getByLabel(/Raw expression/i)).not.toBeVisible()

      await closeStepEditorPanel(app)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('verifies Parameters panel displays conditional fields by loop type', async ({ app }) => {
    await startWorkflowWithTrigger(app)

    await openAddStepPanel(app)
    await selectCategoryAndStepType(app, 'Logic', 'Loop')
    await configureLoopStep(app, { type: 'while' })

    await expect(app.getByRole('textbox', { name: 'Name', exact: true })).toBeVisible()
    await expect(app.getByText('Type', { exact: true })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Type', exact: true })).toContainText('While')
    await expect(app.getByText('Conditional expression', { exact: true })).toBeVisible()
    await expect(app.getByRole('button', { name: /Expression editor mode/i })).toBeVisible()
    await expect(app.getByText('Max iterations', { exact: true })).toBeVisible()
    await expect(app.getByRole('spinbutton', { name: /Max iterations/i })).toBeVisible()

    await configureLoopStep(app, { type: 'forEach' })

    await expect(app.getByText('Items expression', { exact: true })).toBeVisible()
    await expect(app.getByRole('textbox', { name: 'Items expression', exact: true })).toBeVisible()
    await expect(app.getByText('Item variable', { exact: true })).toBeVisible()
    await expect(app.getByRole('textbox', { name: 'Item variable', exact: true })).toBeVisible()
    await expect(app.getByText('Index variable', { exact: true })).toBeVisible()
    await expect(app.getByRole('textbox', { name: 'Index variable', exact: true })).toBeVisible()
    await expect(app.getByRole('button', { name: /Expression editor mode/i })).not.toBeVisible()

    await app.getByRole('button', { name: 'Cancel' }).click()
  })

  const loopBodyTestCases = [
    {
      type: 'While',
      addLoop: (app: Parameters<typeof addWhileLoopStep>[0]) =>
        addWhileLoopStep(app, {
          name: 'While with body',
          condition: '${counter} < 5',
        }),
      workflowPrefix: 'e2e-loop-while-body',
      loopNodeName: 'While with body',
      scriptName: 'Loop body action',
      scriptCode: 'print("loop iteration")',
    },
    {
      type: 'For Each',
      addLoop: (app: Parameters<typeof addForEachLoopStep>[0]) =>
        addForEachLoopStep(app, {
          name: 'For each with body',
          items: '${input.items}',
        }),
      workflowPrefix: 'e2e-loop-foreach-body',
      loopNodeName: 'For each with body',
      scriptName: 'Process each item',
      scriptCode: 'print(item)',
    },
  ] as const

  for (const testCase of loopBodyTestCases) {
    test(`connects child node to Loop (${testCase.type}) body`, async ({ app }) => {
      const workflowName = buildUniqueName(testCase.workflowPrefix)

      try {
        await startWorkflowWithTrigger(app)
        await testCase.addLoop(app)
        await verifyStepVisible(app, testCase.loopNodeName)

        await addChildScriptToLoopStep(app, testCase.scriptName, testCase.scriptCode, testCase.loopNodeName)
        await waitForUIReady(app)

        await verifyStepVisible(app, testCase.loopNodeName)
        await verifyStepVisible(app, testCase.scriptName)

        await saveWorkflow(app, workflowName)

        await expect(app.getByPlaceholder('Workflow name')).toHaveValue(workflowName)
      } finally {
        await deleteWorkflow(app, workflowName)
      }
    })
  }

  test('loop-back edge renders after save and reopen', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-loop-back-reopen')

    try {
      await startWorkflowWithTrigger(app)

      await addWhileLoopStep(app, {
        name: 'Loop header',
        condition: 'true',
      })
      await addChildScriptToLoopStep(app, 'Loop body', 'print("body")', 'Loop header')
      await waitForUIReady(app)
      await triggerLayout(app)

      const edgePathCountBeforeSave = await app.locator('svg g.react-flow__edge path').count()
      expect(edgePathCountBeforeSave).toBeGreaterThanOrEqual(2)

      await saveWorkflow(app, workflowName)
      const workflowId = app.url().match(/workflow-builder\/([^/?]+)/)?.[1]
      expect(workflowId).toBeTruthy()

      await openWorkflowInBuilder(app, workflowName, workflowId)
      await verifyStepVisible(app, 'Loop header')
      await verifyStepVisible(app, 'Loop body')
      await triggerLayout(app)

      const edgePaths = await app.evaluate(() =>
        [...document.querySelectorAll('svg g.react-flow__edge path')]
          .map((path) => path.getAttribute('d'))
          .filter((path): path is string => Boolean(path))
      )

      expect(edgePaths.length).toBeGreaterThanOrEqual(2)
      edgePaths.forEach((path) => expect(path.trim()).toMatch(/^M/))
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('verifies configuration persists after multiple edits', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-loop-multi-edit')

    try {
      await startWorkflowWithTrigger(app)

      await addForEachLoopStep(app, {
        name: 'Initial loop',
        items: '${input.list}',
        itemVariable: 'item',
        indexVariable: 'idx',
      })

      // First edit - change items and add maxIterations (before workflow save)
      await openStepForEditing(app, 'Initial loop')
      await configureLoopStep(app, {
        items: '${trigger.data}',
        maxIterations: 50,
      })
      await saveAndCloseStepForm(app)

      // Second edit - change itemVariable (still before workflow save)
      await openStepForEditing(app, 'Initial loop')
      await configureLoopStep(app, {
        itemVariable: 'element',
      })
      await saveAndCloseStepForm(app)

      // Now save the workflow with all the edits
      await saveWorkflow(app, workflowName)

      // Verify all changes persisted
      await openStepForEditing(app, 'Initial loop')

      await expect(app.getByRole('textbox', { name: 'Items expression', exact: true })).toHaveValue('${trigger.data}')
      await expect(app.getByRole('textbox', { name: 'Item variable', exact: true })).toHaveValue('element')
      await expect(app.getByRole('textbox', { name: 'Index variable', exact: true })).toHaveValue('idx')
      await expect(app.getByRole('spinbutton', { name: /Max iterations/i })).toHaveValue('50')

      await closeStepEditorPanel(app)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })
})

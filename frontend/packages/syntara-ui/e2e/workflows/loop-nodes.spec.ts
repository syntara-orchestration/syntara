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
import { openAddNodePanel, selectCategoryAndType } from '../helpers/v2-nodes'
import {
  addChildScriptToLoop,
  addForEachLoopNode,
  addWhileLoopNode,
  configureLoopNode,
  saveAndCloseNodeForm,
} from '../helpers/v2-nodes-loop'
import {
  buildUniqueName,
  closeNodeEditorPanel,
  deleteWorkflow,
  openNodeForEditing,
  saveWorkflow,
  startWorkflowWithTrigger,
  verifyNodeVisible,
  waitForUIReady,
} from '../helpers/workflows'

test.describe('Loop Node Configuration [UI-16]', () => {
  test('adds Loop (While) node with condition', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-loop-while')

    try {
      await startWorkflowWithTrigger(app)

      await addWhileLoopNode(app, {
        name: 'While loop',
        condition: '${counter} < 10',
      })

      await verifyNodeVisible(app, 'While loop')
      await saveWorkflow(app, workflowName)

      await expect(app).toHaveURL(/workflow-builder\/.+/)
      await expect(app.getByPlaceholder('Workflow name')).toHaveValue(workflowName)
      await verifyNodeVisible(app, 'While loop')
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('adds Loop (For Each) node with items expression', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-loop-foreach')

    try {
      await startWorkflowWithTrigger(app)

      await addForEachLoopNode(app, {
        name: 'For each loop',
        items: '${trigger.items}',
      })

      await verifyNodeVisible(app, 'For each loop')
      await saveWorkflow(app, workflowName)

      await expect(app).toHaveURL(/workflow-builder\/.+/)
      await expect(app.getByPlaceholder('Workflow name')).toHaveValue(workflowName)
      await verifyNodeVisible(app, 'For each loop')
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('verifies custom item and index variables persist', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-loop-foreach-vars')

    try {
      await startWorkflowWithTrigger(app)

      await addForEachLoopNode(app, {
        name: 'Process items',
        items: '${input.records}',
        itemVariable: 'record',
        indexVariable: 'recordIndex',
      })

      await verifyNodeVisible(app, 'Process items')
      await saveWorkflow(app, workflowName)

      await openNodeForEditing(app, 'Process items')

      await expect(app.getByRole('textbox', { name: 'Name', exact: true })).toHaveValue('Process items')
      await expect(app.getByRole('button', { name: 'Type', exact: true })).toContainText('For each')
      await expect(app.getByRole('textbox', { name: 'Items expression', exact: true })).toHaveValue('${input.records}')
      await expect(app.getByRole('textbox', { name: 'Item variable', exact: true })).toHaveValue('record')
      await expect(app.getByRole('textbox', { name: 'Index variable', exact: true })).toHaveValue('recordIndex')

      await closeNodeEditorPanel(app)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('verifies max iterations persist on Loop (While)', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-loop-while-maxiter')

    try {
      await startWorkflowWithTrigger(app)

      await addWhileLoopNode(app, {
        name: 'Limited while loop',
        condition: 'true',
        maxIterations: 100,
      })

      await verifyNodeVisible(app, 'Limited while loop')
      await saveWorkflow(app, workflowName)

      await openNodeForEditing(app, 'Limited while loop')

      await expect(app.getByRole('textbox', { name: 'Name', exact: true })).toHaveValue('Limited while loop')
      await expect(app.getByRole('button', { name: 'Type', exact: true })).toContainText('While')
      await expect(app.getByLabel(/Raw expression/i)).toHaveValue('true')
      await expect(app.getByRole('spinbutton', { name: /Max iterations/i })).toHaveValue('100')

      await closeNodeEditorPanel(app)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('verifies loop type switch from While to For Each persists', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-loop-type-switch')

    try {
      await startWorkflowWithTrigger(app)

      await openAddNodePanel(app)
      await selectCategoryAndType(app, 'Logic', 'Loop')
      await configureLoopNode(app, {
        name: 'Switchable loop',
        type: 'while',
        condition: 'true',
      })
      await saveAndCloseNodeForm(app)

      await verifyNodeVisible(app, 'Switchable loop')

      await openNodeForEditing(app, 'Switchable loop')
      await configureLoopNode(app, {
        type: 'forEach',
        items: '${input.data}',
      })
      await saveAndCloseNodeForm(app)

      await saveWorkflow(app, workflowName)

      await openNodeForEditing(app, 'Switchable loop')

      await expect(app.getByRole('button', { name: 'Type', exact: true })).toContainText('For each')
      await expect(app.getByRole('textbox', { name: 'Items expression', exact: true })).toHaveValue('${input.data}')
      await expect(app.getByLabel(/Raw expression/i)).not.toBeVisible()

      await closeNodeEditorPanel(app)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('verifies Parameters panel displays conditional fields by loop type', async ({ app }) => {
    await startWorkflowWithTrigger(app)

    await openAddNodePanel(app)
    await selectCategoryAndType(app, 'Logic', 'Loop')
    await configureLoopNode(app, { type: 'while' })

    await expect(app.getByRole('textbox', { name: 'Name', exact: true })).toBeVisible()
    await expect(app.getByText('Type', { exact: true })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Type', exact: true })).toContainText('While')
    await expect(app.getByText('Conditional expression', { exact: true })).toBeVisible()
    await expect(app.getByRole('button', { name: /Expression editor mode/i })).toBeVisible()
    await expect(app.getByText('Max iterations', { exact: true })).toBeVisible()
    await expect(app.getByRole('spinbutton', { name: /Max iterations/i })).toBeVisible()

    await configureLoopNode(app, { type: 'forEach' })

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
      addLoop: (app: Parameters<typeof addWhileLoopNode>[0]) =>
        addWhileLoopNode(app, {
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
      addLoop: (app: Parameters<typeof addForEachLoopNode>[0]) =>
        addForEachLoopNode(app, {
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
        await verifyNodeVisible(app, testCase.loopNodeName)

        await addChildScriptToLoop(app, testCase.scriptName, testCase.scriptCode)
        await waitForUIReady(app)

        await verifyNodeVisible(app, testCase.loopNodeName)
        await verifyNodeVisible(app, testCase.scriptName)

        await saveWorkflow(app, workflowName)

        await expect(app).toHaveURL(/workflow-builder\/.+/)
        await expect(app.getByPlaceholder('Workflow name')).toHaveValue(workflowName)
      } finally {
        await deleteWorkflow(app, workflowName)
      }
    })
  }

  test('verifies configuration persists after multiple edits', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-loop-multi-edit')

    try {
      await startWorkflowWithTrigger(app)

      await addForEachLoopNode(app, {
        name: 'Initial loop',
        items: '${input.list}',
        itemVariable: 'item',
        indexVariable: 'idx',
      })

      // First edit - change items and add maxIterations (before workflow save)
      await openNodeForEditing(app, 'Initial loop')
      await configureLoopNode(app, {
        items: '${trigger.data}',
        maxIterations: 50,
      })
      await saveAndCloseNodeForm(app)

      // Second edit - change itemVariable (still before workflow save)
      await openNodeForEditing(app, 'Initial loop')
      await configureLoopNode(app, {
        itemVariable: 'element',
      })
      await saveAndCloseNodeForm(app)

      // Now save the workflow with all the edits
      await saveWorkflow(app, workflowName)

      // Verify all changes persisted
      await openNodeForEditing(app, 'Initial loop')

      await expect(app.getByRole('textbox', { name: 'Items expression', exact: true })).toHaveValue('${trigger.data}')
      await expect(app.getByRole('textbox', { name: 'Item variable', exact: true })).toHaveValue('element')
      await expect(app.getByRole('textbox', { name: 'Index variable', exact: true })).toHaveValue('idx')
      await expect(app.getByRole('spinbutton', { name: /Max iterations/i })).toHaveValue('50')

      await closeNodeEditorPanel(app)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })
})

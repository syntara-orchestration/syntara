import { test, expect, toAppUrl } from './fixtures'
import { addManualTrigger, addConditionNodeWithBranch } from './helpers/v2-nodes'
import {
  addConvergeNodeWithAllStrategy,
  addConvergeNodeWithAnyStrategy,
  addConvergeNodeWithTimeout,
  createWorkflowWithBranchesForConverge,
  expectConvergeNodeConfig,
  openConvergeFormOnNewWorkflow,
} from './helpers/v2-nodes-converge'
import { cancelAndCloseEditor, getWorkflowPayload } from './helpers/workflow-payload'
import {
  addNodePanel,
  selectProjectIfRequired,
  deleteWorkflow,
  openWorkflowInBuilder,
  triggerLayout,
} from './helpers/workflows'

test.describe('Converge Node - E2E Tests', () => {
  test.describe('Catalog', () => {
    test('Select converge node from Logic category', async ({ app }) => {
      try {
        await app.goto(toAppUrl('/workflow-builder/new'))
        await addManualTrigger(app, 'Manual trigger')
        await addConditionNodeWithBranch(app, 'Condition', 'true')

        const layoutButton = app.getByRole('button', { name: 'Layout' })
        if ((await layoutButton.count()) > 0) {
          await layoutButton.click()
        }

        const addBtns = app.locator('.react-flow').getByRole('button', { name: 'Add connected step' })
        await expect(addBtns).not.toHaveCount(0, { timeout: 10_000 })
        const [addBtn] = await addBtns.all()
        await expect(addBtn).toBeVisible()
        await addBtn.click({ force: true })

        const panel = addNodePanel(app)
        await expect(panel).toHaveCount(1)
        await panel.getByRole('button', { name: 'Logic', exact: true }).click()
        const convergeBtn = panel.getByRole('button', { name: 'Converge', exact: true })
        await expect(convergeBtn).toBeVisible()
        await convergeBtn.click()

        await expect(app.getByRole('button', { name: 'Continue when criteria', exact: true })).toBeVisible()
        await expect(app.getByRole('button', { name: 'Continue when criteria', exact: true })).toContainText(
          'All branches reach this step'
        )
        // Wait duration DurationInput is always visible (no toggle switch)
        await expect(app.getByText('Wait duration')).toBeVisible()
      } finally {
        await cancelAndCloseEditor(app)
      }
    })

    test('Cancel adding converge node', async ({ app }) => {
      await openConvergeFormOnNewWorkflow(app)

      await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Test Converge')
      await app.getByRole('button', { name: 'Continue when criteria', exact: true }).click()
      await app.getByRole('option', { name: 'Any branches reach this step' }).click()

      const cancelButton = app.getByRole('button', { name: 'Cancel step creation' })
      await expect(cancelButton).toBeVisible()
      await cancelButton.click()

      await expect(app.getByRole('button', { name: 'Continue when criteria', exact: true })).not.toBeVisible()
      await expect(app.getByText('Test Converge')).not.toBeVisible()
    })
  })

  test.describe('Wait for all branches', () => {
    test('Create converge node with "all" strategy (default)', async ({ app }) => {
      const wfName = await createWorkflowWithBranchesForConverge(app)

      try {
        await addConvergeNodeWithAllStrategy(app, 'Converge All')

        const saveRequestPromise = app.waitForRequest(
          (req) => req.url().includes('/workflows') && req.method() === 'POST'
        )
        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        const saveRequest = await saveRequestPromise

        await expect(app.getByText('Converge All')).toBeVisible()
        const payload = getWorkflowPayload(saveRequest)
        expectConvergeNodeConfig(payload.workflow_definition.nodes, { strategy: 'all' })
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })

    test('Edit existing converge node with "all" strategy', async ({ app }) => {
      const wfName = await createWorkflowWithBranchesForConverge(app)

      try {
        await addConvergeNodeWithAllStrategy(app, 'Converge All')
        await triggerLayout(app)

        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        await expect(app).toHaveURL(/workflow-builder\/(?!new\b).+/)

        await openWorkflowInBuilder(app, wfName)
        await app.getByText('Converge All').click()

        await expect(app.getByRole('button', { name: 'Continue when criteria', exact: true })).toContainText(
          'All branches reach this step'
        )

        await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Updated Converge')
        await app.getByRole('button', { name: 'Update' }).click()

        const saveRequestPromise = app.waitForRequest(
          (req) => req.url().includes('/workflows') && req.method() === 'PATCH'
        )
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        const saveRequest = await saveRequestPromise

        const payload = getWorkflowPayload(saveRequest)
        const convergeNode = payload.workflow_definition.nodes.find((n) => n.type === 'converge')
        expect(convergeNode?.name).toBe('Updated Converge')
        expect(convergeNode?.parameters.strategy).toBe('all')
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })

    test('Switch from "any" to "all" strategy', async ({ app }) => {
      const wfName = await createWorkflowWithBranchesForConverge(app)

      try {
        await addConvergeNodeWithAnyStrategy(app, 'Converge Any', 2)
        await triggerLayout(app)

        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        await expect(app).toHaveURL(/workflow-builder\/(?!new\b).+/)

        await openWorkflowInBuilder(app, wfName)
        await app.getByText('Converge Any').click()

        await app.getByRole('button', { name: 'Continue when criteria', exact: true }).click()
        await app.getByRole('option', { name: 'All branches reach this step' }).click()

        await expect(
          app.getByRole('spinbutton', { name: /Required number of branches before continuing/i })
        ).not.toBeVisible()

        await app.getByRole('button', { name: 'Update' }).click()

        const saveRequestPromise = app.waitForRequest(
          (req) => req.url().includes('/workflows') && req.method() === 'PATCH'
        )
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        const saveRequest = await saveRequestPromise

        const payload = getWorkflowPayload(saveRequest)
        expectConvergeNodeConfig(payload.workflow_definition.nodes, { strategy: 'all' })
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })
  })

  test.describe('Wait for N of M branches', () => {
    test('Create converge node with "any" strategy and valid N', async ({ app }) => {
      const wfName = await createWorkflowWithBranchesForConverge(app)

      try {
        await addConvergeNodeWithAnyStrategy(app, 'Converge Any', 1)

        const saveRequestPromise = app.waitForRequest(
          (req) => req.url().includes('/workflows') && req.method() === 'POST'
        )
        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        const saveRequest = await saveRequestPromise

        const payload = getWorkflowPayload(saveRequest)
        expectConvergeNodeConfig(payload.workflow_definition.nodes, { strategy: 'any', n_required: 1 })
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })

    test('Edit converge node with "any" strategy', async ({ app }) => {
      const wfName = await createWorkflowWithBranchesForConverge(app)

      try {
        await addConvergeNodeWithAnyStrategy(app, 'Converge Any', 2)
        await triggerLayout(app)

        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        await expect(app).toHaveURL(/workflow-builder\/(?!new\b).+/)

        await openWorkflowInBuilder(app, wfName)
        await app.getByText('Converge Any').click()

        const requiredPathCountInput = app.getByRole('spinbutton', {
          name: /Required number of branches before continuing/i,
        })
        await expect(requiredPathCountInput).toHaveValue('2')

        await requiredPathCountInput.fill('1')
        await app.getByRole('button', { name: 'Update' }).click()

        const saveRequestPromise = app.waitForRequest(
          (req) => req.url().includes('/workflows') && req.method() === 'PATCH'
        )
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        const saveRequest = await saveRequestPromise

        const payload = getWorkflowPayload(saveRequest)
        expectConvergeNodeConfig(payload.workflow_definition.nodes, { strategy: 'any', n_required: 1 })
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })

    test('Switch from "all" to "any" strategy', async ({ app }) => {
      const wfName = await createWorkflowWithBranchesForConverge(app)

      try {
        await addConvergeNodeWithAllStrategy(app, 'Converge All')
        await triggerLayout(app)

        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        await expect(app).toHaveURL(/workflow-builder\/(?!new\b).+/)

        await openWorkflowInBuilder(app, wfName)
        await app.getByText('Converge All').click()

        await app.getByRole('button', { name: 'Continue when criteria', exact: true }).click()
        await app.getByRole('option', { name: 'Any branches reach this step' }).click()

        const requiredPathCountInput = app.getByRole('spinbutton', {
          name: /Required number of branches before continuing/i,
        })
        await expect(requiredPathCountInput).toBeVisible()
        await expect(requiredPathCountInput).toHaveValue('1')

        await requiredPathCountInput.fill('2')
        await app.getByRole('button', { name: 'Update' }).click()

        const saveRequestPromise = app.waitForRequest(
          (req) => req.url().includes('/workflows') && req.method() === 'PATCH'
        )
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        const saveRequest = await saveRequestPromise

        const payload = getWorkflowPayload(saveRequest)
        expectConvergeNodeConfig(payload.workflow_definition.nodes, { strategy: 'any', n_required: 2 })
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })

    test('Round-trip persistence of "any" strategy configuration', async ({ app }) => {
      const wfName = await createWorkflowWithBranchesForConverge(app)

      try {
        await addConvergeNodeWithAnyStrategy(app, 'Converge Any Persist', 5)
        await triggerLayout(app)

        const saveRequestPromise = app.waitForRequest(
          (req) => req.url().includes('/workflows') && req.method() === 'POST'
        )
        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        const saveRequest = await saveRequestPromise

        const payload = getWorkflowPayload(saveRequest)
        expectConvergeNodeConfig(payload.workflow_definition.nodes, { strategy: 'any', n_required: 5 })

        await expect(app).toHaveURL(/workflow-builder\/(?!new\b).+/)
        await openWorkflowInBuilder(app, wfName)

        await app.getByText('Converge Any Persist').click()
        await expect(app.getByRole('button', { name: 'Continue when criteria', exact: true })).toContainText(
          'Any branches reach this step'
        )
        await expect(
          app.getByRole('spinbutton', { name: /Required number of branches before continuing/i })
        ).toHaveValue('5')
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })
  })

  test.describe('Timeout configuration', () => {
    test('Enable timeout and configure units', async ({ app }) => {
      const wfName = await createWorkflowWithBranchesForConverge(app)

      try {
        await addConvergeNodeWithTimeout(app, 'Converge Timeout', {
          seconds: 30,
          minutes: 5,
          hours: 2,
          days: 1,
          action: 'fail',
        })

        const saveRequestPromise = app.waitForRequest(
          (req) => req.url().includes('/workflows') && req.method() === 'POST'
        )
        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        const saveRequest = await saveRequestPromise

        // 30 + (5*60) + (2*3600) + (1*86400) = 93930
        const payload = getWorkflowPayload(saveRequest)
        expectConvergeNodeConfig(payload.workflow_definition.nodes, {
          strategy: 'all',
          wait_duration: 93930,
        })
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })

    test('Edit existing converge node with timeout', async ({ app }) => {
      const wfName = await createWorkflowWithBranchesForConverge(app)

      try {
        await addConvergeNodeWithTimeout(app, 'Converge Timeout', {
          minutes: 5,
          action: 'continue',
        })
        await triggerLayout(app)

        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        await expect(app).toHaveURL(/workflow-builder\/(?!new\b).+/)

        await openWorkflowInBuilder(app, wfName)
        await app.getByText('Converge Timeout').click()

        // Wait for edit panel to be ready
        await expect(app.getByRole('tab', { name: 'Parameters' })).toBeVisible()
        await expect(app.getByText('Wait duration')).toBeVisible()

        await expect(app.getByLabel(/Minutes/i)).toHaveValue('5')
        await expect(app.getByLabel(/Seconds/i)).toHaveValue('0')
        await expect(app.getByLabel(/Hours/i)).toHaveValue('0')
        await expect(app.getByLabel(/Days/i)).toHaveValue('0')
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })

    test('Wait duration persists after editing', async ({ app }) => {
      const wfName = await createWorkflowWithBranchesForConverge(app)

      try {
        await addConvergeNodeWithTimeout(app, 'Converge Wait Edit', {
          minutes: 10,
        })
        await triggerLayout(app)

        const saveRequestPromise = app.waitForRequest(
          (req) => req.url().includes('/workflows') && req.method() === 'POST'
        )
        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        const saveRequest = await saveRequestPromise

        const payload = getWorkflowPayload(saveRequest)
        expectConvergeNodeConfig(payload.workflow_definition.nodes, {
          strategy: 'all',
          wait_duration: 600,
        })

        await expect(app).toHaveURL(/workflow-builder\/(?!new\b).+/)
        await openWorkflowInBuilder(app, wfName)

        await app.getByText('Converge Wait Edit').click()
        await expect(app.getByRole('tab', { name: 'Parameters' })).toBeVisible()

        await expect(app.getByLabel(/Minutes/i)).toHaveValue('10')
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })

    test('Complex timeout values round-trip correctly', async ({ app }) => {
      const wfName = await createWorkflowWithBranchesForConverge(app)

      try {
        await addConvergeNodeWithTimeout(app, 'Converge Complex Timeout', {
          seconds: 45,
          minutes: 30,
          hours: 12,
          days: 2,
          action: 'continue',
        })
        await triggerLayout(app)

        const saveRequestPromise = app.waitForRequest(
          (req) => req.url().includes('/workflows') && req.method() === 'POST'
        )
        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        const saveRequest = await saveRequestPromise

        // 45 + (30*60) + (12*3600) + (2*86400) = 217845
        const payload = getWorkflowPayload(saveRequest)
        expectConvergeNodeConfig(payload.workflow_definition.nodes, {
          strategy: 'all',
          wait_duration: 217845,
        })

        await expect(app).toHaveURL(/workflow-builder\/(?!new\b).+/)
        await openWorkflowInBuilder(app, wfName)

        await app.getByText('Converge Complex Timeout').click()

        await expect(app.getByLabel(/Seconds/i)).toHaveValue('45')
        await expect(app.getByLabel(/Minutes/i)).toHaveValue('30')
        await expect(app.getByLabel(/Hours/i)).toHaveValue('12')
        await expect(app.getByLabel(/Days/i)).toHaveValue('2')
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })

    test('Timeout with "any" strategy', async ({ app }) => {
      const wfName = await createWorkflowWithBranchesForConverge(app)

      try {
        await addConvergeNodeWithTimeout(app, 'Converge Any Timeout', {
          minutes: 20,
          action: 'continue',
          strategy: 'any',
          requiredPathCount: 2,
        })

        const saveRequestPromise = app.waitForRequest(
          (req) => req.url().includes('/workflows') && req.method() === 'POST'
        )
        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        const saveRequest = await saveRequestPromise

        const payload = getWorkflowPayload(saveRequest)
        expectConvergeNodeConfig(payload.workflow_definition.nodes, {
          strategy: 'any',
          n_required: 2,
          wait_duration: 1200,
        })
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })
  })
})

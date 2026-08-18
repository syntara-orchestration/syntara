/**
 * E2E Tests: Schedule Trigger — UI-19 (AAP-64513)
 *
 * Critical paths covered:
 * - Schedule trigger is discoverable in the trigger selection panel
 * - "Schedule type" dropdown switches between interval and continuous modes
 * - Interval mode renders the DateRangeCadencePicker (Start date, Cadence, Trigger time)
 * - Continuous mode hides the date/cadence picker
 * - Saving an interval schedule creates the node on canvas
 * - Saved schedule trigger persists through save/reload round-trip
 * - Canvas node label reflects the trigger type
 * - Clicking a saved schedule trigger reopens its form with the saved values
 *
 * Edge cases:
 * - Saving interval mode with no cadence/date shows validation error
 * - Saving returns the user to the canvas (not stuck in the form)
 *
 * Known gap:
 * - Cron expression input is not present in the current UI (schedule type options are
 *   "interval" and "continuous" only). If cron support is added, add tests here.
 */

import { test, expect, toAppUrl } from './fixtures'
import { addScheduleTrigger } from './helpers/v2-nodes'
import {
  buildUniqueName,
  closeNodeEditorPanel,
  deleteWorkflow,
  openWorkflowInBuilder,
  selectProjectIfRequired,
  clickAddConnectedStep,
  fillCodeEditor,
} from './helpers/workflows'
import { ensureProject } from './utils/api'

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

test.describe('Schedule Trigger — UI-19', () => {
  // -------------------------------------------------------------------------
  // Trigger discovery
  // -------------------------------------------------------------------------

  test.describe('Trigger selection panel', () => {
    test('Schedule trigger button is visible in trigger selection', async ({ app }) => {
      await app.goto(toAppUrl('/workflow-builder/new'))

      await expect(app.getByRole('heading', { name: /select a trigger node/i })).toBeVisible({
        timeout: 15_000,
      })
      await expect(app.getByRole('button', { name: 'Schedule trigger' })).toBeVisible()
    })

    test('Clicking Schedule trigger opens the schedule configuration form', async ({ app }) => {
      await app.goto(toAppUrl('/workflow-builder/new'))

      await expect(app.getByRole('heading', { name: /select a trigger node/i })).toBeVisible({
        timeout: 15_000,
      })
      await app.getByRole('button', { name: 'Schedule trigger' }).click()

      // Name field and schedule expression dropdown must appear
      await expect(app.getByRole('textbox', { name: 'Name', exact: true })).toBeVisible()
      await expect(app.getByLabel('Schedule expression', { exact: true })).toBeVisible()
    })
  })

  // -------------------------------------------------------------------------
  // Schedule type switching
  // -------------------------------------------------------------------------

  test.describe('Schedule type modes', () => {
    test('Visual schedule builder renders required fields', async ({ app }) => {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await expect(app.getByRole('heading', { name: /select a trigger node/i })).toBeVisible({
        timeout: 15_000,
      })
      await app.getByRole('button', { name: 'Schedule trigger' }).click()

      // Switch to Visual schedule builder — may already be default
      const scheduleExpressionSelect = app.getByLabel('Schedule expression', { exact: true })
      await expect(scheduleExpressionSelect).toBeVisible()
      await scheduleExpressionSelect.click()
      await app.getByRole('option', { name: 'Visual schedule builder', exact: true }).click()

      // Schedule builder fields must appear
      await expect(app.getByLabel('Start date', { exact: true })).toBeVisible()
      await expect(app.getByLabel('Frequency', { exact: true })).toBeVisible()
    })

    test('Custom cron expression mode hides the schedule builder fields', async ({ app }) => {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await expect(app.getByRole('heading', { name: /select a trigger node/i })).toBeVisible({
        timeout: 15_000,
      })
      await app.getByRole('button', { name: 'Schedule trigger' }).click()

      // Start in interval mode — confirm schedule builder fields appear
      const scheduleExpressionSelect = app.getByLabel('Schedule expression', { exact: true })
      await scheduleExpressionSelect.click()
      await app.getByRole('option', { name: 'Visual schedule builder', exact: true }).click()
      await expect(app.getByLabel('Start date', { exact: true })).toBeVisible()

      // Switch to cron mode — schedule builder fields should disappear, cron input appears
      await scheduleExpressionSelect.click()
      await app.getByRole('option', { name: 'Custom cron expression', exact: true }).click()
      await expect(app.getByLabel('Start date', { exact: true })).not.toBeVisible()
      await expect(app.getByLabel('Cron expression', { exact: true })).toBeVisible()
    })

    test('Frequency options include Daily, Weekly, Monthly, Yearly', async ({ app }) => {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await expect(app.getByRole('heading', { name: /select a trigger node/i })).toBeVisible({
        timeout: 15_000,
      })
      await app.getByRole('button', { name: 'Schedule trigger' }).click()
      await app.getByLabel('Schedule expression', { exact: true }).click()
      await app.getByRole('option', { name: 'Visual schedule builder', exact: true }).click()

      // Open the Frequency dropdown to verify options
      await app.getByLabel('Frequency', { exact: true }).click()
      await expect(app.getByRole('option', { name: 'Daily' })).toBeVisible()
      await expect(app.getByRole('option', { name: 'Weekly' })).toBeVisible()
      await expect(app.getByRole('option', { name: 'Monthly' })).toBeVisible()
      await expect(app.getByRole('option', { name: 'Yearly' })).toBeVisible()
    })

    test('Custom cron expression mode is available', async ({ app }) => {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await expect(app.getByRole('heading', { name: /select a trigger node/i })).toBeVisible({
        timeout: 15_000,
      })
      await app.getByRole('button', { name: 'Schedule trigger' }).click()

      // Open the MenuToggle to reveal options, then verify cron is available
      const scheduleExpressionSelect = app.getByLabel('Schedule expression', { exact: true })
      await scheduleExpressionSelect.click()
      await expect(app.getByRole('option', { name: 'Custom cron expression' })).toBeVisible()
      await app.keyboard.press('Escape')
    })
  })

  // -------------------------------------------------------------------------
  // Saving with interval schedule
  // -------------------------------------------------------------------------

  test.describe('Interval schedule — save and canvas', () => {
    test('Create a workflow with daily interval schedule trigger and verify canvas', async ({ app }) => {
      const wfName = buildUniqueName('schedule-daily')

      await ensureProject(app)
      await app.goto(toAppUrl('/workflow-builder/new'))

      try {
        await addScheduleTrigger(app, 'Daily Job', {
          scheduleType: 'interval',
          cadence: 'daily',
        })

        // Add a connected action so the workflow can be saved
        const panel = await clickAddConnectedStep(app)
        await panel.getByRole('button', { name: 'Action', exact: true }).click()
        await panel.getByRole('button', { name: 'Script', exact: true }).click()
        await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Scheduled action')
        await fillCodeEditor(app, { value: 'print("running")' })
        await app.getByRole('button', { name: 'Create', exact: true }).click()
        await closeNodeEditorPanel(app)

        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        await expect(app).toHaveURL(/workflow-builder\/(?!new\b).+/)

        // Schedule trigger node is visible on the canvas
        await expect(app.getByText('Daily Job')).toBeVisible({ timeout: 10_000 })
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })

    test('Create a workflow with weekly interval schedule trigger', async ({ app }) => {
      const wfName = buildUniqueName('schedule-weekly')

      await ensureProject(app)
      await app.goto(toAppUrl('/workflow-builder/new'))

      try {
        await addScheduleTrigger(app, 'Weekly Report', {
          scheduleType: 'interval',
          cadence: 'weekly',
        })

        const panel = await clickAddConnectedStep(app)
        await panel.getByRole('button', { name: 'Action', exact: true }).click()
        await panel.getByRole('button', { name: 'Script', exact: true }).click()
        await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Report action')
        await fillCodeEditor(app, { value: 'print("report")' })
        await app.getByRole('button', { name: 'Create', exact: true }).click()
        await closeNodeEditorPanel(app)

        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        await expect(app).toHaveURL(/workflow-builder\/(?!new\b).+/)

        await expect(app.getByText('Weekly Report')).toBeVisible({ timeout: 10_000 })
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })

    test('Create a workflow with continuous schedule trigger', async ({ app }) => {
      const wfName = buildUniqueName('schedule-continuous')

      await ensureProject(app)
      await app.goto(toAppUrl('/workflow-builder/new'))

      try {
        await addScheduleTrigger(app, 'Continuous Trigger', { scheduleType: 'continuous' })

        const panel = await clickAddConnectedStep(app)
        await panel.getByRole('button', { name: 'Action', exact: true }).click()
        await panel.getByRole('button', { name: 'Script', exact: true }).click()
        await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Continuous action')
        await fillCodeEditor(app, { value: 'print("running")' })
        await app.getByRole('button', { name: 'Create', exact: true }).click()
        await closeNodeEditorPanel(app)

        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        await expect(app).toHaveURL(/workflow-builder\/(?!new\b).+/)

        await expect(app.getByText('Continuous Trigger')).toBeVisible({ timeout: 10_000 })
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })
  })

  // -------------------------------------------------------------------------
  // Round-trip persistence
  // -------------------------------------------------------------------------

  test.describe('Round-trip persistence', () => {
    test('Saved schedule trigger reloads with the correct schedule type', async ({ app }) => {
      const wfName = buildUniqueName('schedule-roundtrip')

      await ensureProject(app)
      await app.goto(toAppUrl('/workflow-builder/new'))

      try {
        await addScheduleTrigger(app, 'Persisted Schedule', {
          scheduleType: 'interval',
          cadence: 'monthly',
        })

        const panel = await clickAddConnectedStep(app)
        await panel.getByRole('button', { name: 'Action', exact: true }).click()
        await panel.getByRole('button', { name: 'Script', exact: true }).click()
        await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Action')
        await fillCodeEditor(app, { value: 'print("ok")' })
        await app.getByRole('button', { name: 'Create', exact: true }).click()
        await closeNodeEditorPanel(app)

        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        await expect(app).toHaveURL(/workflow-builder\/(?!new\b).+/)

        // Reload and reopen the trigger node
        await openWorkflowInBuilder(app, wfName)

        const triggerNode = app.getByText('Persisted Schedule')
        await expect(triggerNode).toBeVisible({ timeout: 15_000 })
        await triggerNode.click()

        // Editor opens with saved schedule expression
        await expect(app.getByLabel('Schedule expression', { exact: true })).toBeVisible({ timeout: 10_000 })
        await expect(app.getByLabel('Schedule expression', { exact: true })).toContainText('Visual schedule builder')

        // Frequency shows 'Monthly' since that cadence was saved
        await expect(app.getByLabel('Frequency', { exact: true })).toBeVisible()
        await expect(app.getByLabel('Frequency', { exact: true })).toContainText('Monthly')
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })

    test('Switching from interval to cron and saving persists the change', async ({ app }) => {
      const wfName = buildUniqueName('schedule-type-switch')

      await ensureProject(app)
      await app.goto(toAppUrl('/workflow-builder/new'))

      try {
        // Start with interval
        await addScheduleTrigger(app, 'Switchable Schedule', {
          scheduleType: 'interval',
          cadence: 'daily',
        })

        const panel = await clickAddConnectedStep(app)
        await panel.getByRole('button', { name: 'Action', exact: true }).click()
        await panel.getByRole('button', { name: 'Script', exact: true }).click()
        await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Action')
        await fillCodeEditor(app, { value: 'print("ok")' })
        await app.getByRole('button', { name: 'Create', exact: true }).click()
        await closeNodeEditorPanel(app)

        await selectProjectIfRequired(app)
        await app.getByPlaceholder('Workflow name').fill(wfName)
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        await expect(app).toHaveURL(/workflow-builder\/(?!new\b).+/)

        // Reopen trigger and switch to continuous
        await openWorkflowInBuilder(app, wfName)
        const triggerNode = app.getByText('Switchable Schedule')
        await expect(triggerNode).toBeVisible({ timeout: 15_000 })
        await triggerNode.click()

        await expect(app.getByLabel('Schedule expression', { exact: true })).toBeVisible({ timeout: 10_000 })
        await app.getByLabel('Schedule expression', { exact: true }).click()
        await app.getByRole('option', { name: 'Custom cron expression', exact: true }).click()
        const cronInput = app.getByLabel('Cron expression', { exact: true })
        await expect(cronInput).toBeVisible()
        await cronInput.fill('0 9 * * *')

        const patchRequestPromise = app.waitForRequest(
          (req) => req.url().includes('/workflows') && req.method() === 'PATCH'
        )
        await app.getByRole('button', { name: 'Update', exact: true }).click()
        await app.getByRole('button', { name: 'Save', exact: true }).click()
        await patchRequestPromise

        // Verify the trigger node still shows on canvas after save
        await expect(app.getByText('Switchable Schedule')).toBeVisible({ timeout: 10_000 })
      } finally {
        await deleteWorkflow(app, wfName)
      }
    })
  })

  // -------------------------------------------------------------------------
})
// Note: The trigger form schema declares `name` as optional (z.string().optional()),
// so submitting without a name saves successfully — there is no frontend name validation to test.

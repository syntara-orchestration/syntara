/**
 * Form Trigger — run from Workflows list
 *
 * Test plan: UI-4, UI-6, UI-7, UI-8 (Form Trigger list-run procedure).
 *
 * | AC   | Coverage |
 * |------|----------|
 * | AC-1 | UI-6 / UI-8 — modal opens before execution starts |
 * | AC-2 | UI-4 — client required-field + server FORM_VALIDATION_ERROR mapping |
 * | AC-3 | UI-7 — submit label, CSS override, success message |
 * | AC-4 | UI-8 — submit navigates to execution; input_data matches form |
 * | AC-5 | execution:run — Run published version disabled for viewer |
 * | AC-6 | UI-4 pre-run — invalid form definition; no form-trigger run modal, no execution |
 */
import { test, expect, toAppUrl } from '../fixtures'
import { executionIdFromPageUrl } from '../helpers/formResponses'
import {
  createPublishedFormTriggerWorkflow,
  disposeFormTriggerWorkflow,
  expectFormTriggerRunModal,
  readExecutionInputData,
  registerStripFormDefinitionFromWorkflowApi,
  startRunPublishedFromWorkflowList,
  unregisterStripFormDefinitionFromWorkflowApi,
} from '../helpers/formTriggerRun'
import { openRowKebab, pfWidget } from '../helpers/patternfly'

const CUSTOM_FORM_MESSAGE = 'Describe why you are starting this run.'
const CUSTOM_SUBMIT_LABEL = 'Start workflow'
const CUSTOM_SUCCESS_MESSAGE = 'Form trigger run accepted.'
const SERVER_VALIDATION_MESSAGE = 'Rejected by server for E2E'
/** Backend publish validation rejects attribute selectors in css_override. */
const FORM_TRIGGER_CSS_OVERRIDE = '.form-step-response-form label { color: rgb(170, 0, 0) !important; }'

const EXECUTIONS_POST_ROUTE = '**/api/v1/executions'

test.describe('Form trigger — run from workflows list', { tag: '@pr-check' }, () => {
  test('AC-1 / UI-6: opens the run modal before execution starts (no manual run confirmation)', async ({ app }) => {
    const created = await createPublishedFormTriggerWorkflow(app, { namePrefix: 'e2e-form-trigger-ui6' })

    try {
      await startRunPublishedFromWorkflowList(app, created.workflowName)
      await expect(app).not.toHaveURL(/\/executions\//)
      await expect(app.getByRole('heading', { name: 'Run workflow?' })).not.toBeVisible()
      await expectFormTriggerRunModal(app, {
        workflowName: created.workflowName,
        triggerName: created.triggerName,
        message: 'Complete the form to start this workflow.',
      })
    } finally {
      await disposeFormTriggerWorkflow(app, created.workflowId)
    }
  })

  test('AC-2 / UI-4: blocks submit until required fields are filled in the run modal', async ({ app }) => {
    const created = await createPublishedFormTriggerWorkflow(app, {
      namePrefix: 'e2e-form-trigger-ui4',
      parameters: { message: CUSTOM_FORM_MESSAGE, submit_label: CUSTOM_SUBMIT_LABEL },
    })

    try {
      await startRunPublishedFromWorkflowList(app, created.workflowName)
      await expectFormTriggerRunModal(app, {
        workflowName: created.workflowName,
        triggerName: created.triggerName,
        message: CUSTOM_FORM_MESSAGE,
      })

      await expect(app.getByRole('textbox', { name: 'Summary' })).toBeVisible()
      await expect(app.getByLabel('Score')).toBeVisible()

      await app.getByRole('button', { name: CUSTOM_SUBMIT_LABEL }).click()
      await expect(app.getByText('This field is required')).toBeVisible({ timeout: 10_000 })
      await expect(app).not.toHaveURL(/\/executions\//)

      await app.getByRole('textbox', { name: 'Summary' }).fill('E2E form trigger summary')
      await app.getByRole('button', { name: CUSTOM_SUBMIT_LABEL }).click()

      await expect(app).toHaveURL(/\/executions\//, { timeout: 30_000 })
    } finally {
      await disposeFormTriggerWorkflow(app, created.workflowId)
    }
  })

  test('AC-2 / UI-4: maps server FORM_VALIDATION_ERROR responses to form fields', async ({ app }) => {
    const created = await createPublishedFormTriggerWorkflow(app, {
      namePrefix: 'e2e-form-trigger-server-validation',
      parameters: { submit_label: CUSTOM_SUBMIT_LABEL },
    })

    await app.route(EXECUTIONS_POST_ROUTE, async (route) => {
      if (route.request().method() !== 'POST') {
        await route.continue()
        return
      }
      await route.fulfill({
        status: 422,
        contentType: 'application/json',
        body: JSON.stringify({
          type: 'about:blank',
          title: 'Validation Error',
          code: 'FORM_VALIDATION_ERROR',
          detail: `Form validation failed: summary: ${SERVER_VALIDATION_MESSAGE}`,
        }),
      })
    })

    try {
      await startRunPublishedFromWorkflowList(app, created.workflowName)
      await app.getByRole('textbox', { name: 'Summary' }).fill('Passes client validation')
      await app.getByRole('button', { name: CUSTOM_SUBMIT_LABEL }).click()

      await expect(app.getByText(SERVER_VALIDATION_MESSAGE)).toBeVisible({ timeout: 15_000 })
      await expect(app).not.toHaveURL(/\/executions\//)
      await expect(app.getByTestId('form-trigger-run-form')).toBeVisible()
    } finally {
      await app.unroute(EXECUTIONS_POST_ROUTE)
      await disposeFormTriggerWorkflow(app, created.workflowId)
    }
  })

  test('AC-6 / UI-4: pre-run failure shows Cannot run workflow without opening the form-trigger run modal', async ({
    app,
  }) => {
    const created = await createPublishedFormTriggerWorkflow(app, { namePrefix: 'e2e-form-trigger-invalid' })
    await registerStripFormDefinitionFromWorkflowApi(app, created.workflowId)

    try {
      await startRunPublishedFromWorkflowList(app, created.workflowName)
      await expect(app.getByRole('heading', { name: 'Run workflow?' })).toBeVisible()
      await app.getByRole('button', { name: 'Run now' }).click()

      const runBlockedToast = pfWidget(app, 'Alert').filter({ hasText: 'Cannot run workflow' })
      await expect(runBlockedToast).toBeVisible({ timeout: 15_000 })
      await expect(runBlockedToast).toContainText('invalid or empty form definition')
      await expect(app.getByTestId('form-trigger-run-form')).not.toBeVisible()
      await expect(app).not.toHaveURL(/\/executions\//)
    } finally {
      await unregisterStripFormDefinitionFromWorkflowApi(app, created.workflowId)
      await disposeFormTriggerWorkflow(app, created.workflowId)
    }
  })

  test('AC-3 / UI-7: shows customized submit label, styling, and success message in the run modal', async ({ app }) => {
    const created = await createPublishedFormTriggerWorkflow(app, {
      namePrefix: 'e2e-form-trigger-ui7',
      parameters: {
        message: CUSTOM_FORM_MESSAGE,
        submit_label: CUSTOM_SUBMIT_LABEL,
        success_message: CUSTOM_SUCCESS_MESSAGE,
        css_override: FORM_TRIGGER_CSS_OVERRIDE,
      },
    })

    try {
      await startRunPublishedFromWorkflowList(app, created.workflowName)
      await expectFormTriggerRunModal(app, {
        workflowName: created.workflowName,
        triggerName: created.triggerName,
        message: CUSTOM_FORM_MESSAGE,
      })
      await expect(app.getByRole('button', { name: CUSTOM_SUBMIT_LABEL })).toBeVisible()
      await expect(app.getByText('Summary', { exact: true })).toHaveCSS('color', 'rgb(170, 0, 0)')

      await app.getByRole('textbox', { name: 'Summary' }).fill('Custom styling run')
      await app.getByRole('button', { name: CUSTOM_SUBMIT_LABEL }).click()

      await expect(app.getByText(CUSTOM_SUCCESS_MESSAGE)).toBeVisible({ timeout: 15_000 })
      await expect(app).toHaveURL(/\/executions\//, { timeout: 30_000 })
    } finally {
      await disposeFormTriggerWorkflow(app, created.workflowId)
    }
  })

  test('AC-4 / UI-8: list run submits values and navigates to execution details', async ({ app }) => {
    const created = await createPublishedFormTriggerWorkflow(app, {
      namePrefix: 'e2e-form-trigger-ui8',
      parameters: { submit_label: CUSTOM_SUBMIT_LABEL },
    })

    const summaryValue = 'E2E form trigger list run'
    const scoreValue = '7'

    try {
      await startRunPublishedFromWorkflowList(app, created.workflowName)
      await expect(app).not.toHaveURL(/\/executions\//)
      await expectFormTriggerRunModal(app, {
        workflowName: created.workflowName,
        triggerName: created.triggerName,
      })

      await app.getByRole('textbox', { name: 'Summary' }).fill(summaryValue)
      await app.getByLabel('Score').fill(scoreValue)
      await app.getByRole('button', { name: CUSTOM_SUBMIT_LABEL }).click()

      await expect(app).toHaveURL(/\/executions\//, { timeout: 30_000 })
      const executionId = executionIdFromPageUrl(app)

      const inputData = await readExecutionInputData(app, executionId)
      expect(inputData['summary']).toBe(summaryValue)
      expect(String(inputData['score'])).toBe(scoreValue)
    } finally {
      await disposeFormTriggerWorkflow(app, created.workflowId)
    }
  })

  test('AC-5: execution:run permission disables Run published version for viewer role', async ({ app, viewerApp }) => {
    const created = await createPublishedFormTriggerWorkflow(app, { namePrefix: 'e2e-form-trigger-rbac' })

    try {
      await viewerApp.goto(toAppUrl('/workflows'))
      await viewerApp.getByPlaceholder('Filter by name').fill(created.workflowName)
      await viewerApp.getByRole('button', { name: 'Apply filter' }).click()

      const workflowRow = viewerApp
        .getByRole('grid', { name: 'Workflows table' })
        .getByRole('row', { name: new RegExp(created.workflowName) })
      await expect(workflowRow).toBeVisible({ timeout: 15_000 })
      await openRowKebab(workflowRow, /Edit workflow/i)

      await expect(viewerApp.getByRole('menuitem', { name: /Run published version/i })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
    } finally {
      await disposeFormTriggerWorkflow(app, created.workflowId)
    }
  })
})

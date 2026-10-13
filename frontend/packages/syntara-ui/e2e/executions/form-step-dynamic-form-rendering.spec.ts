/**
 * Form step — SynDynamicForm responder rendering gaps
 *
 * - UI-4: Multi-field required validation in the execution detail panel
 * - UI-7: Custom submit label, success message, and CSS overrides on the rendered form
 * - UI-8: Run published workflow from the Workflows list (no pre-run modal), then respond in panel
 */
import { test, expect } from '../fixtures'
import { openExecutionFormPromptDeepLink, waitForFormPromptPanel } from '../helpers/formPromptPanel'
import {
  MULTI_FIELD_FORM_DEFINITION,
  createPendingFormStepWorkflow,
  disposeFormPromptWorkflow,
  executionIdFromPageUrl,
} from '../helpers/formResponses'
import { clickWhenEnabled } from '../helpers/patternfly'
import { runPublishedWorkflowFromList } from '../helpers/workflow-run'

const CUSTOM_SUBMIT_LABEL = 'Send form step'
const CUSTOM_SUCCESS_MESSAGE = 'Form step saved for this run.'
const CUSTOM_FORM_MESSAGE = 'Please complete the form step fields below.'
const FORM_STEP_CSS_OVERRIDE =
  '.form-step-response-form label[for="syn-dynamic-form-summary"] { color: rgb(170, 0, 0) !important; }'

test.describe('Form step — SynDynamicForm rendering', { tag: '@pr-check' }, () => {
  test('UI-4: blocks submit until required fields are filled across multiple field types', async ({ app }) => {
    const created = await createPendingFormStepWorkflow(app, {
      namePrefix: 'e2e-multi-field',
      parameters: {
        message: CUSTOM_FORM_MESSAGE,
        form_definition: MULTI_FIELD_FORM_DEFINITION,
        submit_label: CUSTOM_SUBMIT_LABEL,
      },
    })

    try {
      await openExecutionFormPromptDeepLink(app, created.executionId, created.formPromptId, {
        expectedMessage: CUSTOM_FORM_MESSAGE,
      })

      await expect(app.getByRole('textbox', { name: 'Summary' })).toBeVisible()
      await expect(app.getByLabel('Score')).toBeVisible()

      await app.getByRole('button', { name: CUSTOM_SUBMIT_LABEL }).click()
      await expect(app.getByText('This field is required')).toBeVisible({ timeout: 10_000 })

      await app.getByRole('textbox', { name: 'Summary' }).fill('E2E multi-field summary')
      await app.getByRole('button', { name: CUSTOM_SUBMIT_LABEL }).click()

      await expect(app.getByRole('heading', { name: 'Respond to prompt' })).not.toBeVisible({ timeout: 15_000 })
    } finally {
      await disposeFormPromptWorkflow(app, created.workflowId, created.executionId)
    }
  })

  test('UI-7: shows customized submit label, success message, and CSS overrides', async ({ app }) => {
    const created = await createPendingFormStepWorkflow(app, {
      namePrefix: 'e2e-form-customization',
      parameters: {
        message: CUSTOM_FORM_MESSAGE,
        form_definition: MULTI_FIELD_FORM_DEFINITION,
        submit_label: CUSTOM_SUBMIT_LABEL,
        success_message: CUSTOM_SUCCESS_MESSAGE,
        css_override: FORM_STEP_CSS_OVERRIDE,
      },
    })

    try {
      await openExecutionFormPromptDeepLink(app, created.executionId, created.formPromptId, {
        expectedMessage: CUSTOM_FORM_MESSAGE,
      })

      await expect(app.getByRole('button', { name: CUSTOM_SUBMIT_LABEL })).toBeVisible()

      await expect(app.locator('label[for="syn-dynamic-form-summary"]')).toHaveCSS('color', 'rgb(170, 0, 0)')

      await app.getByRole('textbox', { name: 'Summary' }).fill('Customization probe')
      await app.getByRole('button', { name: CUSTOM_SUBMIT_LABEL }).click()

      const successAlert = app.locator('[data-ouia-component-type="PF6/Alert"]').filter({ hasText: 'Form submitted' })
      await expect(successAlert).toBeVisible({ timeout: 15_000 })
      await expect(successAlert).toContainText(CUSTOM_SUCCESS_MESSAGE)
    } finally {
      await disposeFormPromptWorkflow(app, created.workflowId, created.executionId)
    }
  })

  test('UI-8: runs from the Workflows list and completes the waiting form step in the panel', async ({ app }) => {
    test.slow()
    const created = await createPendingFormStepWorkflow(app, {
      namePrefix: 'e2e-form-step-run-list',
      runAfterPublish: false,
      parameters: {
        message: CUSTOM_FORM_MESSAGE,
        submit_label: CUSTOM_SUBMIT_LABEL,
      },
    })

    let executionId = ''
    try {
      await runPublishedWorkflowFromList(app, created.workflowName)
      executionId = executionIdFromPageUrl(app)

      await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
      await expect(app.getByText(CUSTOM_FORM_MESSAGE)).toBeVisible({ timeout: 30_000 })

      const respondButton = app.getByRole('button', { name: 'Respond to prompt' })
      await expect(async () => {
        if (
          !(await app
            .getByRole('heading', { name: 'Respond to prompt' })
            .isVisible()
            .catch(() => false))
        ) {
          await clickWhenEnabled(respondButton, { timeout: 10_000 })
        }
        await waitForFormPromptPanel(app, { expectedMessage: CUSTOM_FORM_MESSAGE })
      }).toPass({ timeout: 45_000, intervals: [2_000] })

      await app.getByRole('textbox', { name: 'Answer' }).fill('Run from workflows list')
      await app.getByRole('button', { name: CUSTOM_SUBMIT_LABEL }).click()
      await expect(app.getByRole('heading', { name: 'Respond to prompt' })).not.toBeVisible({ timeout: 15_000 })
    } finally {
      await disposeFormPromptWorkflow(app, created.workflowId, executionId || undefined)
    }
  })
})

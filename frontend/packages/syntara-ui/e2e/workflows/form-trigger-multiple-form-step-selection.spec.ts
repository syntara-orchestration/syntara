/**
 * E2E Tests (UI-9): Form Trigger Multiple-Trigger Selection
 *
 * When a published workflow has multiple form steps, running from the workflows list
 * must prompt the user to choose a form step, open the matching form, and avoid
 * starting an execution when the selector is dismissed.
 */

import { test, expect, toAppUrl } from '../fixtures'
import { buildUniqueName } from '../helpers/workflows'
import { createWorkflowViaApi, deleteWorkflowViaApi, publishWorkflowViaApi } from '../utils/api'

const FIRST_FORM_STEP_NAME = 'Intake alpha'
const SECOND_FORM_STEP_NAME = 'Intake beta'
const FIRST_FIELD_LABEL = 'Alpha reason'
const SECOND_FIELD_LABEL = 'Beta reason'

function formTriggerParameters(fieldLabel: string, valueName: string) {
  return {
    form_definition: {
      fields: [{ type: 'text', value_name: valueName, label: fieldLabel, required: true }],
    },
  }
}

async function openRunPublishedFromWorkflowList(app: import('../fixtures').Page, workflowName: string): Promise<void> {
  await app.goto(toAppUrl('/workflows'))
  await app.getByPlaceholder('Filter by name').fill(workflowName)
  await app.getByRole('button', { name: 'Apply filter' }).click()

  const row = app.getByRole('row', { name: new RegExp(workflowName) })
  await expect(row).toBeVisible({ timeout: 15_000 })

  await row.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })
  await app.getByRole('menuitem', { name: 'Run published version' }).click()
}

test.describe('Form trigger multiple form step selection', () => {
  test('chooses a form step from the list run flow and dismisses without starting a run', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-multi-form-step')
    const { id: workflowId, versionNumber } = await createWorkflowViaApi({
      app,
      name: workflowName,
      triggers: [
        {
          id: 'form_trigger_a',
          type: 'form_trigger',
          name: FIRST_FORM_STEP_NAME,
          parameters: formTriggerParameters(FIRST_FIELD_LABEL, 'alpha_reason'),
        },
        {
          id: 'form_trigger_b',
          type: 'form_trigger',
          name: SECOND_FORM_STEP_NAME,
          parameters: formTriggerParameters(SECOND_FIELD_LABEL, 'beta_reason'),
        },
      ],
      nodes: [
        {
          id: 'action_1',
          type: 'script',
          name: 'Script',
          parameters: { language: 'python', code: 'print("done")' },
        },
      ],
      edges: [
        { from: 'form_trigger_a', to: 'action_1' },
        { from: 'form_trigger_b', to: 'action_1' },
      ],
    })

    try {
      await publishWorkflowViaApi(app, workflowId, versionNumber)
      await openRunPublishedFromWorkflowList(app, workflowName)

      const chooseDialog = app.getByRole('dialog', { name: 'Run workflow' })
      await expect(chooseDialog).toBeVisible({ timeout: 15_000 })
      await expect(chooseDialog.getByRole('menuitem', { name: FIRST_FORM_STEP_NAME })).toBeVisible()
      await expect(chooseDialog.getByRole('menuitem', { name: SECOND_FORM_STEP_NAME })).toBeVisible()

      await app.keyboard.press('Escape')
      await expect(chooseDialog).not.toBeVisible()
      await expect(app).toHaveURL(/\/workflows/)

      await openRunPublishedFromWorkflowList(app, workflowName)
      const chooseDialogAgain = app.getByRole('dialog', { name: 'Run workflow' })
      await expect(chooseDialogAgain).toBeVisible({ timeout: 15_000 })
      await chooseDialogAgain.getByRole('menuitem', { name: SECOND_FORM_STEP_NAME }).click()

      const runFormDialog = app.getByRole('dialog', { name: new RegExp(`Run ${SECOND_FORM_STEP_NAME} form`) })
      await expect(runFormDialog).toBeVisible()
      await expect(runFormDialog.getByRole('textbox', { name: SECOND_FIELD_LABEL })).toBeVisible()
      await expect(runFormDialog.getByRole('textbox', { name: FIRST_FIELD_LABEL })).not.toBeVisible()

      await runFormDialog.getByRole('textbox', { name: SECOND_FIELD_LABEL }).fill('beta submission')
      await runFormDialog.getByRole('button', { name: 'Submit' }).click()

      await expect(app).toHaveURL(/\/executions\//, { timeout: 30_000 })
    } finally {
      await deleteWorkflowViaApi(app, workflowId)
    }
  })
})

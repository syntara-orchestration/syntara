/**
 * E2E Tests: Form trigger — SynFormFieldBuilder
 *
 * Covers form field builder scenarios UI-1 through UI-3 on the form_trigger trigger.
 * UI-3 assumes advisory save for form triggers (invalid fields persist via Update); merge PR #1105 first.
 */
import { test, expect } from '../fixtures'
import {
  FORM_FIELD_TYPE_MENU_LABELS,
  type FormFieldBuilderHost,
  type FormFieldTypeMenuLabel,
  clickAddFormField,
  expectFormFieldPlaceholderValue,
  expectFormFieldRequiredChecked,
  expectFormFieldTypeLabel,
  fieldLabelValuesInOrder,
  formFieldBuilderCard,
  reorderFormField,
  removeFormField,
  selectFormFieldType,
  setFormFieldLabel,
  setFormFieldPlaceholder,
  setFormFieldRequired,
  setFormFieldValueName,
  workflowIdFromUrl,
} from '../helpers/formFieldBuilder'
import { expectDangerToast } from '../helpers/formPromptRbac'
import {
  createFormTriggerWorkflowWithBuilderOpen,
  readFormTriggerDefinitionFromApi,
  reloadBuilderAndReopenFormTrigger,
  saveFormTriggerAndWorkflow,
} from '../helpers/formTriggerBuilder'
import { buildUniqueName, deleteWorkflow } from '../helpers/workflows'

const FORM_TRIGGER_HOST: FormFieldBuilderHost = 'form_trigger'
const FORM_TRIGGER_NAME = 'Launch form'
const VALIDATION_BANNER_TIMEOUT = 20_000

type Ui1FieldSpec = { label: string; type: FormFieldTypeMenuLabel; placeholder?: string }

const UI1_FIELD_SPECS: Ui1FieldSpec[] = [
  { label: 'E2E Text', type: FORM_FIELD_TYPE_MENU_LABELS.text, placeholder: 'Text placeholder' },
  { label: 'E2E Text area', type: FORM_FIELD_TYPE_MENU_LABELS.textarea, placeholder: 'Area placeholder' },
  { label: 'E2E Masked', type: FORM_FIELD_TYPE_MENU_LABELS.maskedText, placeholder: '••••' },
  { label: 'E2E Email', type: FORM_FIELD_TYPE_MENU_LABELS.email, placeholder: 'you@example.com' },
  { label: 'E2E Number', type: FORM_FIELD_TYPE_MENU_LABELS.number },
  { label: 'E2E Checkbox', type: FORM_FIELD_TYPE_MENU_LABELS.checkbox },
  { label: 'E2E Date', type: FORM_FIELD_TYPE_MENU_LABELS.date },
  { label: 'E2E Dropdown', type: FORM_FIELD_TYPE_MENU_LABELS.dropdown },
  { label: 'E2E Multi-select', type: FORM_FIELD_TYPE_MENU_LABELS.multiSelect },
]

test.describe('Form trigger — form field builder', { tag: '@pr-check' }, () => {
  test.describe.configure({ mode: 'serial' })

  test('UI-1: configures all supported field types and persists after save and reload', async ({ app }) => {
    test.slow()
    const workflowName = buildUniqueName('e2e-form-trigger-builder-ui1')

    try {
      await createFormTriggerWorkflowWithBuilderOpen(app, workflowName, FORM_TRIGGER_NAME)

      for (const [index, spec] of UI1_FIELD_SPECS.entries()) {
        const fieldNumber = index + 1
        if (index > 0) {
          await clickAddFormField(app, FORM_TRIGGER_HOST)
        }
        await setFormFieldLabel(app, fieldNumber, spec.label, FORM_TRIGGER_HOST)
        await selectFormFieldType(app, fieldNumber, spec.type, FORM_TRIGGER_HOST)
        if (spec.placeholder !== undefined) {
          await setFormFieldPlaceholder(app, fieldNumber, spec.placeholder, FORM_TRIGGER_HOST)
        }
        if (index === 0) {
          await setFormFieldRequired(app, fieldNumber, true, FORM_TRIGGER_HOST)
        }
      }

      await app.getByRole('button', { name: 'Preview form' }).click()
      const previewDialog = app.getByRole('dialog')
      await expect(previewDialog.getByRole('heading', { name: 'Preview form' })).toBeVisible()
      await expect(previewDialog.getByText(UI1_FIELD_SPECS[0].label, { exact: true })).toBeVisible()
      await previewDialog.getByRole('button', { name: 'Close' }).click()
      await expect(previewDialog).not.toBeVisible()

      await expect(app.getByRole('textbox', { name: /Field label|Checkbox label/ })).toHaveCount(UI1_FIELD_SPECS.length)

      await saveFormTriggerAndWorkflow(app)
      const workflowId = workflowIdFromUrl(app)

      const stored = await readFormTriggerDefinitionFromApi(app, workflowId)
      expect(stored.fields).toHaveLength(UI1_FIELD_SPECS.length)
      expect(stored.fields.map((field) => field.label)).toEqual(UI1_FIELD_SPECS.map((spec) => spec.label))
      expect(stored.fields.map((field) => field.type)).toEqual([
        'text',
        'textarea',
        'masked_text',
        'email',
        'number',
        'checkbox',
        'date',
        'dropdown',
        'multi_select',
      ])
      expect(stored.fields[0]?.required).toBe(true)

      await reloadBuilderAndReopenFormTrigger(app, FORM_TRIGGER_NAME)
      await expect(async () => {
        const labels = await fieldLabelValuesInOrder(app, FORM_TRIGGER_HOST)
        expect(labels).toEqual(UI1_FIELD_SPECS.map((spec) => spec.label))
      }).toPass({ timeout: 15_000 })

      for (const [index, spec] of UI1_FIELD_SPECS.entries()) {
        const fieldNumber = index + 1
        await expectFormFieldTypeLabel(app, fieldNumber, spec.type, FORM_TRIGGER_HOST)
        if (spec.placeholder !== undefined) {
          await expectFormFieldPlaceholderValue(app, fieldNumber, spec.placeholder, FORM_TRIGGER_HOST)
        }
        if (index === 0) {
          await expectFormFieldRequiredChecked(app, fieldNumber, true, FORM_TRIGGER_HOST)
        }
      }
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('UI-2: adds, removes, reorders, and changes field types in the builder', async ({ app }) => {
    test.slow()
    const workflowName = buildUniqueName('e2e-form-trigger-builder-ui2')

    try {
      await createFormTriggerWorkflowWithBuilderOpen(app, workflowName, FORM_TRIGGER_NAME)

      await clickAddFormField(app, FORM_TRIGGER_HOST)
      await setFormFieldLabel(app, 1, 'First text', FORM_TRIGGER_HOST)
      await setFormFieldLabel(app, 2, 'Second number', FORM_TRIGGER_HOST)
      await selectFormFieldType(app, 2, FORM_FIELD_TYPE_MENU_LABELS.number, FORM_TRIGGER_HOST)

      await removeFormField(app, 1, FORM_TRIGGER_HOST)
      await expect(app.getByRole('textbox', { name: 'Field label' })).toHaveCount(1)
      await expect(app.getByRole('textbox', { name: 'Field label' })).toHaveValue('Second number')

      await clickAddFormField(app, FORM_TRIGGER_HOST)
      await clickAddFormField(app, FORM_TRIGGER_HOST)
      await clickAddFormField(app, FORM_TRIGGER_HOST)
      await setFormFieldLabel(app, 1, 'Alpha', FORM_TRIGGER_HOST)
      await setFormFieldLabel(app, 2, 'Beta', FORM_TRIGGER_HOST)
      await setFormFieldLabel(app, 3, 'Gamma', FORM_TRIGGER_HOST)
      await setFormFieldLabel(app, 4, 'Delta', FORM_TRIGGER_HOST)

      await reorderFormField(app, 4, 1, { assertFirstLabel: 'Delta', host: FORM_TRIGGER_HOST })

      await selectFormFieldType(app, 4, FORM_FIELD_TYPE_MENU_LABELS.checkbox, FORM_TRIGGER_HOST)
      await expect(formFieldBuilderCard(app, 4, FORM_TRIGGER_HOST).getByRole('textbox', { name: 'Checkbox label' })).toBeVisible()

      await selectFormFieldType(app, 4, FORM_FIELD_TYPE_MENU_LABELS.dropdown, FORM_TRIGGER_HOST)
      await expect(formFieldBuilderCard(app, 4, FORM_TRIGGER_HOST).getByRole('button', { name: 'Add option' })).toBeVisible()

      await saveFormTriggerAndWorkflow(app)
      const workflowId = workflowIdFromUrl(app)
      const stored = await readFormTriggerDefinitionFromApi(app, workflowId)
      expect(stored.fields.map((field) => field.label)).toEqual(['Delta', 'Alpha', 'Beta', 'Gamma'])
      expect(stored.fields.map((field) => field.type)).toEqual(['text', 'number', 'text', 'dropdown'])
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('UI-3: saves with validation warnings and blocks publish and run for invalid fields', async ({ app }) => {
    test.setTimeout(90_000)
    const workflowName = buildUniqueName('e2e-form-trigger-builder-ui3')
    const duplicateValueName = 'shared_name'

    try {
      await createFormTriggerWorkflowWithBuilderOpen(app, workflowName, FORM_TRIGGER_NAME)

      await clickAddFormField(app, FORM_TRIGGER_HOST)
      await setFormFieldLabel(app, 1, 'Field A', FORM_TRIGGER_HOST)
      await setFormFieldLabel(app, 2, 'Field B', FORM_TRIGGER_HOST)
      await setFormFieldValueName(app, 1, duplicateValueName, FORM_TRIGGER_HOST)
      await setFormFieldValueName(app, 2, duplicateValueName, FORM_TRIGGER_HOST)

      // Advisory save (form trigger draft builder): invalid fields persist without blocking Update.
      await saveFormTriggerAndWorkflow(app)
      const workflowId = workflowIdFromUrl(app)

      const saveValidationHeading = app.getByRole('heading', {
        name: /Saved with \d+ (warning|issue)/i,
      })
      await expect(saveValidationHeading).toBeVisible({ timeout: VALIDATION_BANNER_TIMEOUT })
      await app.getByRole('button', { name: /alert details/i }).click()
      await expect(app.getByText(new RegExp(duplicateValueName, 'i'))).toBeVisible({
        timeout: VALIDATION_BANNER_TIMEOUT,
      })

      const publishButton = app.getByRole('button', { name: /publish workflow/i })
      await expect(publishButton).toHaveAttribute('aria-disabled', 'true')

      const runButton = app.getByRole('button', { name: 'Run', exact: true })
      const runBlockedToast = app.getByRole('alert').filter({ hasText: 'Cannot run workflow' })

      await expect(runButton).toBeEnabled({ timeout: 15_000 })
      await runButton.click()
      const runConfirm = app.getByRole('button', { name: /Run now|Save and run/ })
      await expect(runConfirm).toBeVisible({ timeout: 10_000 })
      await runConfirm.click()
      await expect(app).not.toHaveURL(/\/executions\//, { timeout: 15_000 })

      if (await runBlockedToast.isVisible({ timeout: 12_000 }).catch(() => false)) {
        await expectDangerToast(app, 'Cannot run workflow', /duplicate|shared_name|invalid form definition/i)
      }

      await expect(saveValidationHeading).toBeVisible({ timeout: VALIDATION_BANNER_TIMEOUT })

      const stored = await readFormTriggerDefinitionFromApi(app, workflowId)
      expect(stored.fields).toHaveLength(2)
      expect(stored.fields.map((field) => field.value_name)).toEqual([duplicateValueName, duplicateValueName])
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })
})

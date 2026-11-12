/**
 * E2E Tests: Form trigger — SynFormFieldBuilder
 *
 * Covers form field builder scenarios UI-1 through UI-3 on the form_trigger trigger.
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
import {
  createFormTriggerWorkflowWithBuilderOpen,
  expandFormTriggerValidationBannerDetails,
  formTriggerValidationBannerTitle,
  readFormTriggerDefinitionFromApi,
  reloadBuilderAndReopenFormTrigger,
  saveFormTriggerAndWorkflow,
} from '../helpers/formTriggerBuilder'
import { pfWidget } from '../helpers/patternfly'
import { triggerVerifyWorkflow } from '../helpers/workflow-verify'
import { buildUniqueName, deleteWorkflow } from '../helpers/workflows'
import { isRealBackendE2e } from '../playwrightWebServerEnv'

const FORM_TRIGGER_HOST: FormFieldBuilderHost = 'form_trigger'
const FORM_TRIGGER_NAME = 'Launch form'
const VALIDATION_BANNER_TIMEOUT = isRealBackendE2e ? 45_000 : 20_000
const VERIFY_BANNER_PASS_TIMEOUT = isRealBackendE2e ? 90_000 : 60_000

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

      await expect(async () => {
        const labels = await fieldLabelValuesInOrder(app, FORM_TRIGGER_HOST)
        expect(labels).toHaveLength(UI1_FIELD_SPECS.length)
      }).toPass({ timeout: isRealBackendE2e ? 30_000 : 15_000, intervals: [500, 1_000, 2_000] })

      await saveFormTriggerAndWorkflow(app)
      const workflowId = workflowIdFromUrl(app)

      const stored = await readFormTriggerDefinitionFromApi(app, workflowId)
      expect(stored.fields).toHaveLength(UI1_FIELD_SPECS.length)
      expect(stored.fields.map((field) => field.label)).toEqual(UI1_FIELD_SPECS.map((spec) => spec.label))
      expect(
        stored.fields.map((field) =>
          field.type === 'text' ? { type: field.type, display: field.display } : { type: field.type }
        )
      ).toEqual([
        { type: 'text', display: 'single_line' },
        { type: 'text', display: 'multi_line' },
        { type: 'text', display: 'masked' },
        { type: 'email' },
        { type: 'number' },
        { type: 'checkbox' },
        { type: 'date' },
        { type: 'dropdown' },
        { type: 'multi_select' },
      ])
      expect(stored.fields[0]?.required).toBe(true)

      await reloadBuilderAndReopenFormTrigger(app, FORM_TRIGGER_NAME)
      await expect(async () => {
        const labels = await fieldLabelValuesInOrder(app, FORM_TRIGGER_HOST)
        expect(labels).toEqual(UI1_FIELD_SPECS.map((spec) => spec.label))
      }).toPass({ timeout: isRealBackendE2e ? 45_000 : 15_000, intervals: [500, 1_000, 2_000] })

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
      await expect(async () => {
        expect(await fieldLabelValuesInOrder(app, FORM_TRIGGER_HOST)).toEqual(['Second number'])
      }).toPass({ timeout: isRealBackendE2e ? 30_000 : 15_000, intervals: [500, 1_000, 2_000] })

      await clickAddFormField(app, FORM_TRIGGER_HOST)
      await clickAddFormField(app, FORM_TRIGGER_HOST)
      await clickAddFormField(app, FORM_TRIGGER_HOST)
      await setFormFieldLabel(app, 1, 'Alpha', FORM_TRIGGER_HOST)
      await setFormFieldLabel(app, 2, 'Beta', FORM_TRIGGER_HOST)
      await setFormFieldLabel(app, 3, 'Gamma', FORM_TRIGGER_HOST)
      await setFormFieldLabel(app, 4, 'Delta', FORM_TRIGGER_HOST)

      await reorderFormField(app, 4, 1, { assertFirstLabel: 'Delta', host: FORM_TRIGGER_HOST })

      await selectFormFieldType(app, 4, FORM_FIELD_TYPE_MENU_LABELS.checkbox, FORM_TRIGGER_HOST)
      await expect(
        formFieldBuilderCard(app, 4, FORM_TRIGGER_HOST).getByRole('textbox', { name: 'Checkbox label' })
      ).toBeVisible()

      await selectFormFieldType(app, 4, FORM_FIELD_TYPE_MENU_LABELS.dropdown, FORM_TRIGGER_HOST)
      await expect(
        formFieldBuilderCard(app, 4, FORM_TRIGGER_HOST).getByRole('button', { name: 'Add option' })
      ).toBeVisible()

      await app.getByRole('button', { name: 'Preview form' }).click()
      await expect(app.getByRole('heading', { name: 'Preview form' })).toBeVisible()
      await expect(app.getByRole('dialog').getByText('Delta', { exact: true })).toBeVisible()
      await app.keyboard.press('Escape')

      await saveFormTriggerAndWorkflow(app)
      const workflowId = workflowIdFromUrl(app)
      const stored = await readFormTriggerDefinitionFromApi(app, workflowId)
      expect(stored.fields.map((field) => field.label)).toEqual(['Delta', 'Alpha', 'Beta', 'Gamma'])
      expect(stored.fields.map((field) => field.type)).toEqual(['text', 'number', 'text', 'dropdown'])

      await reloadBuilderAndReopenFormTrigger(app, FORM_TRIGGER_NAME)
      await expect(async () => {
        expect(await fieldLabelValuesInOrder(app, FORM_TRIGGER_HOST)).toEqual(['Delta', 'Alpha', 'Beta', 'Gamma'])
      }).toPass({ timeout: isRealBackendE2e ? 45_000 : 15_000, intervals: [500, 1_000, 2_000] })
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('UI-3: saves with validation warnings and blocks publish and run for invalid fields', async ({ app }) => {
    test.slow()
    const workflowName = buildUniqueName('e2e-form-trigger-builder-ui3')
    const duplicateValueName = 'shared_name'

    try {
      await createFormTriggerWorkflowWithBuilderOpen(app, workflowName, FORM_TRIGGER_NAME)

      await clickAddFormField(app, FORM_TRIGGER_HOST)
      await setFormFieldLabel(app, 1, 'Field A', FORM_TRIGGER_HOST)
      await setFormFieldLabel(app, 2, 'Field B', FORM_TRIGGER_HOST)
      await setFormFieldValueName(app, 1, duplicateValueName, FORM_TRIGGER_HOST)
      await setFormFieldValueName(app, 2, duplicateValueName, FORM_TRIGGER_HOST)

      // Advisory save persists invalid fields; canvas validation runs on Verify workflow.
      await saveFormTriggerAndWorkflow(app)
      const workflowId = workflowIdFromUrl(app)

      await expect(formTriggerValidationBannerTitle(app)).toBeVisible({
        timeout: VALIDATION_BANNER_TIMEOUT,
      })

      await expect(async () => {
        await triggerVerifyWorkflow(app)
        await expect(app.getByRole('heading', { name: /Verification failed/i })).toBeVisible({ timeout: 15_000 })
      }).toPass({ timeout: VERIFY_BANNER_PASS_TIMEOUT, intervals: [1_000, 2_000, 3_000] })

      await expandFormTriggerValidationBannerDetails(app)
      await expect(app.getByText(/Duplicate field names|shared_name/i)).toBeVisible({
        timeout: VALIDATION_BANNER_TIMEOUT,
      })

      await expect(app.getByRole('button', { name: /publish workflow/i })).toHaveAttribute('aria-disabled', 'true', {
        timeout: VALIDATION_BANNER_TIMEOUT,
      })

      const runButton = app.getByRole('button', { name: 'Run', exact: true })
      const runBlockedToast = pfWidget(app, 'Alert').filter({ hasText: 'Cannot run workflow' })
      if (await runButton.isEnabled({ timeout: 5_000 }).catch(() => false)) {
        await runButton.click()
        const runConfirm = app.getByRole('button', { name: /Run now|Save and run/ })
        await expect(runConfirm).toBeVisible({ timeout: 10_000 })
        await runConfirm.click()
        await expect(runBlockedToast).toBeVisible({ timeout: 15_000 })
        await expect(app).not.toHaveURL(/\/executions\//)
      } else {
        await expect(runButton).toHaveAttribute('aria-disabled', 'true', { timeout: VALIDATION_BANNER_TIMEOUT })
      }

      const stored = await readFormTriggerDefinitionFromApi(app, workflowId)
      expect(stored.fields).toHaveLength(2)
      expect(stored.fields.map((field) => field.value_name)).toEqual([duplicateValueName, duplicateValueName])
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })
})

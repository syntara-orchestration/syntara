/**
 * E2E Tests: Interactive Prompt — SynFormFieldBuilder (form_prompt node)
 *
 * Covers form field builder scenarios UI-1 through UI-3 on the form_prompt node.
 */
import { test, expect } from '../fixtures'
import {
  FORM_BUILDER_VALIDATION_ALERT,
  FORM_FIELD_TYPE_MENU_LABELS,
  type FormFieldTypeMenuLabel,
  clickAddFormField,
  createFormPromptWorkflowWithBuilderOpen,
  expectFormFieldPlaceholderValue,
  expectFormFieldRequiredChecked,
  expectFormFieldTypeLabel,
  fieldLabelValuesInOrder,
  formFieldBuilderCard,
  readFormPromptDefinitionFromApi,
  reloadBuilderAndReopenFormPrompt,
  removeFormField,
  reorderFormField,
  saveFormPromptNodeAndWorkflow,
  selectFormFieldType,
  setFormFieldLabel,
  setFormFieldPlaceholder,
  setFormFieldRequired,
  setFormFieldValueName,
  workflowIdFromUrl,
} from '../helpers/formFieldBuilder'
import { buildUniqueName, deleteWorkflow } from '../helpers/workflows'

const FORM_PROMPT_NODE_NAME = 'Intake Form'

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

test.describe('Form prompt — form field builder', { tag: '@pr-check' }, () => {
  test('UI-1: configures all supported field types and persists after save and reload', async ({ app }) => {
    test.slow()
    const workflowName = buildUniqueName('e2e-form-builder-ui1')

    try {
      await createFormPromptWorkflowWithBuilderOpen(app, workflowName, FORM_PROMPT_NODE_NAME)

      for (const [index, spec] of UI1_FIELD_SPECS.entries()) {
        const fieldNumber = index + 1
        if (index > 0) {
          await clickAddFormField(app)
        }
        await setFormFieldLabel(app, fieldNumber, spec.label)
        await selectFormFieldType(app, fieldNumber, spec.type)
        if (spec.placeholder !== undefined) {
          await setFormFieldPlaceholder(app, fieldNumber, spec.placeholder)
        }
        if (index === 0) {
          await setFormFieldRequired(app, fieldNumber, true)
        }
      }

      await expect(app.getByRole('textbox', { name: /Field label|Checkbox label/ })).toHaveCount(UI1_FIELD_SPECS.length)

      await saveFormPromptNodeAndWorkflow(app)
      const workflowId = workflowIdFromUrl(app)

      const stored = await readFormPromptDefinitionFromApi(app, workflowId)
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

      await reloadBuilderAndReopenFormPrompt(app, FORM_PROMPT_NODE_NAME)
      await expect(async () => {
        const labels = await fieldLabelValuesInOrder(app)
        expect(labels).toEqual(UI1_FIELD_SPECS.map((spec) => spec.label))
      }).toPass({ timeout: 15_000 })

      for (const [index, spec] of UI1_FIELD_SPECS.entries()) {
        const fieldNumber = index + 1
        await expectFormFieldTypeLabel(app, fieldNumber, spec.type)
        if (spec.placeholder !== undefined) {
          await expectFormFieldPlaceholderValue(app, fieldNumber, spec.placeholder)
        }
        if (index === 0) {
          await expectFormFieldRequiredChecked(app, fieldNumber, true)
        }
      }
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('UI-2: adds, removes, reorders, and changes field types in the builder', async ({ app }) => {
    test.slow()
    const workflowName = buildUniqueName('e2e-form-builder-ui2')

    try {
      await createFormPromptWorkflowWithBuilderOpen(app, workflowName, FORM_PROMPT_NODE_NAME)

      await clickAddFormField(app)
      await setFormFieldLabel(app, 1, 'First text')
      await setFormFieldLabel(app, 2, 'Second number')
      await selectFormFieldType(app, 2, FORM_FIELD_TYPE_MENU_LABELS.number)

      await removeFormField(app, 1)
      await expect(app.getByRole('textbox', { name: 'Field label' })).toHaveCount(1)
      await expect(app.getByRole('textbox', { name: 'Field label' })).toHaveValue('Second number')

      await clickAddFormField(app)
      await clickAddFormField(app)
      await clickAddFormField(app)
      await setFormFieldLabel(app, 1, 'Alpha')
      await setFormFieldLabel(app, 2, 'Beta')
      await setFormFieldLabel(app, 3, 'Gamma')
      await setFormFieldLabel(app, 4, 'Delta')

      await reorderFormField(app, 4, 1)
      await expect(async () => {
        const labels = await fieldLabelValuesInOrder(app)
        expect(labels[0]).toBe('Delta')
      }).toPass({ timeout: 10_000 })

      await selectFormFieldType(app, 4, FORM_FIELD_TYPE_MENU_LABELS.checkbox)
      await expect(formFieldBuilderCard(app, 4).getByRole('textbox', { name: 'Checkbox label' })).toBeVisible()

      await selectFormFieldType(app, 4, FORM_FIELD_TYPE_MENU_LABELS.dropdown)
      await expect(formFieldBuilderCard(app, 4).getByText('Options source', { exact: true })).toBeVisible()

      await saveFormPromptNodeAndWorkflow(app)
      const workflowId = workflowIdFromUrl(app)
      const stored = await readFormPromptDefinitionFromApi(app, workflowId)
      expect(stored.fields.map((field) => field.label)).toEqual(['Delta', 'Alpha', 'Beta', 'Gamma'])
      expect(stored.fields.map((field) => field.type)).toEqual(['text', 'number', 'text', 'dropdown'])
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('UI-3: blocks invalid value names and duplicate value names from persisting', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-form-builder-ui3')

    try {
      await createFormPromptWorkflowWithBuilderOpen(app, workflowName, FORM_PROMPT_NODE_NAME)

      await setFormFieldValueName(app, 1, '1invalid')
      await expect(app.getByText(FORM_BUILDER_VALIDATION_ALERT)).toBeVisible()

      await setFormFieldValueName(app, 1, 'valid_name')
      await expect(app.getByText(FORM_BUILDER_VALIDATION_ALERT)).not.toBeVisible()

      await clickAddFormField(app)
      await setFormFieldLabel(app, 1, 'Field A')
      await setFormFieldLabel(app, 2, 'Field B')
      await setFormFieldValueName(app, 1, 'shared_name')
      await setFormFieldValueName(app, 2, 'shared_name')
      await expect(app.getByText(FORM_BUILDER_VALIDATION_ALERT)).toBeVisible()

      await setFormFieldValueName(app, 2, 'field_b')
      await expect(app.getByText(FORM_BUILDER_VALIDATION_ALERT)).not.toBeVisible()

      await saveFormPromptNodeAndWorkflow(app)
      const workflowId = workflowIdFromUrl(app)
      const stored = await readFormPromptDefinitionFromApi(app, workflowId)
      const valueNames = stored.fields.map((field) => field.value_name)
      expect(new Set(valueNames).size).toBe(valueNames.length)
      expect(valueNames).toContain('shared_name')
      expect(valueNames).toContain('field_b')
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })
})

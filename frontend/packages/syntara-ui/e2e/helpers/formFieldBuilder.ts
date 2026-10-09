/**
 * Helpers for SynFormFieldBuilder on the form_prompt node (workflow builder).
 */
import { expect, type Page } from '../fixtures'
import { apiRequest } from '../utils/api'

import { addFormPromptNodeWithSubmittedBranch } from './v2-nodes'
import {
  clickSaveAndWait,
  closeNodeEditorPanel,
  saveAndCloseNodeForm,
  saveWorkflow,
  startWorkflowWithTrigger,
  triggerLayout,
  waitForUIReady,
} from './workflows'

export const FORM_BUILDER_VALIDATION_ALERT = 'Fix validation errors before changes are saved to the parent form.'

export const FORM_FIELD_TYPE_MENU_LABELS = {
  text: 'Text',
  textarea: 'Text area',
  maskedText: 'Masked text',
  email: 'Email',
  number: 'Number',
  checkbox: 'Checkbox',
  date: 'Date',
  dropdown: 'Dropdown',
  multiSelect: 'Multi-select',
} as const

export type FormFieldTypeMenuLabel = (typeof FORM_FIELD_TYPE_MENU_LABELS)[keyof typeof FORM_FIELD_TYPE_MENU_LABELS]

function formFieldBuilderScope(page: Page) {
  return page
    .locator('#form-prompt-form-fields')
    .locator('xpath=ancestor::*[.//button[contains(normalize-space(.), "Add field")]][1]')
}

async function ensureFieldExpanded(page: Page, fieldNumber: number) {
  const expand = formFieldBuilderScope(page).getByRole('button', { name: `Expand field ${fieldNumber}` })
  if (await expand.isVisible().catch(() => false)) {
    await expand.click()
  }
}

async function scrollFormFieldBuilderIntoView(page: Page) {
  await page.locator('#form-prompt-form-fields').scrollIntoViewIfNeeded()
}

/** Locator for one field card in the builder (1-based index, matches "Reorder field N"). */
export function formFieldBuilderCard(page: Page, fieldNumber: number) {
  const reorder = formFieldBuilderScope(page).getByRole('button', { name: `Reorder field ${fieldNumber}`, exact: true })
  return reorder.locator(
    `xpath=ancestor::*[.//button[starts-with(@aria-label, "Collapse field ${fieldNumber}") or starts-with(@aria-label, "Expand field ${fieldNumber}")]][1]`
  )
}

function formFieldLabelInput(page: Page, fieldNumber: number) {
  return formFieldBuilderCard(page, fieldNumber).getByRole('textbox', { name: /Field label|Checkbox label/ })
}

function formFieldValueNameInput(page: Page, fieldNumber: number) {
  return formFieldBuilderCard(page, fieldNumber).getByRole('textbox', { name: 'Value name' })
}

/** Open the form_prompt node editor (avoids matching branch script nodes whose names contain the form title). */
export async function openFormPromptNodeForEditing(page: Page, nodeName: string) {
  await triggerLayout(page)
  const node = page
    .locator('[role="group"][aria-roledescription="node"].react-flow__node-form_prompt')
    .filter({ has: page.getByText(nodeName, { exact: true }) })
  await waitForUIReady(page)

  const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
  await expect(async () => {
    await expect(node).toBeVisible({ timeout: 5_000 })
    await node.dblclick({ force: true, timeout: 5_000 })
    await expect(nameInput).toHaveValue(nodeName, { timeout: 5_000 })
  }).toPass({ timeout: 30_000, intervals: [500, 1_000, 2_000] })
}

export async function clickAddFormField(page: Page) {
  await scrollFormFieldBuilderIntoView(page)
  const scope = formFieldBuilderScope(page)
  await expect(scope.getByText(FORM_BUILDER_VALIDATION_ALERT)).not.toBeVisible({ timeout: 10_000 })
  const reorderButtons = scope.getByRole('button', { name: /^Reorder field \d+$/ })
  const countBefore = await reorderButtons.count()
  const addField = scope.getByRole('button', { name: 'Add field' })
  await expect(async () => {
    if ((await reorderButtons.count()) === countBefore) {
      await addField.scrollIntoViewIfNeeded()
      await addField.click()
    }
    await expect(reorderButtons).toHaveCount(countBefore + 1, { timeout: 2_000 })
  }).toPass({ timeout: 15_000 })
}

export async function setFormFieldLabel(page: Page, fieldNumber: number, label: string) {
  await scrollFormFieldBuilderIntoView(page)
  const labelBox = formFieldLabelInput(page, fieldNumber)
  await labelBox.scrollIntoViewIfNeeded()
  await labelBox.fill(label)
}

export async function setFormFieldValueName(page: Page, fieldNumber: number, valueName: string) {
  await scrollFormFieldBuilderIntoView(page)
  await ensureFieldExpanded(page, fieldNumber)
  const valueNameInput = formFieldValueNameInput(page, fieldNumber)
  await valueNameInput.scrollIntoViewIfNeeded()
  await valueNameInput.fill(valueName)
  await valueNameInput.blur()
}

export async function setFormFieldPlaceholder(page: Page, fieldNumber: number, placeholder: string) {
  await scrollFormFieldBuilderIntoView(page)
  await ensureFieldExpanded(page, fieldNumber)
  const card = formFieldBuilderCard(page, fieldNumber)
  const placeholderInput = card.getByRole('textbox', { name: 'Placeholder' })
  if (await placeholderInput.isVisible().catch(() => false)) {
    await placeholderInput.fill(placeholder)
  }
}

export async function setFormFieldRequired(page: Page, fieldNumber: number, checked: boolean) {
  await scrollFormFieldBuilderIntoView(page)
  await ensureFieldExpanded(page, fieldNumber)
  const card = formFieldBuilderCard(page, fieldNumber)
  const required = card.getByRole('checkbox', { name: 'Required' })
  if ((await required.isChecked()) === checked) {
    return
  }
  await required.focus()
  await page.keyboard.press('Space')
  await expect(required).toBeChecked({ checked })
}

const FIELD_TYPE_TOGGLE_NAME = /^(Text|Text area|Masked text|Email|Number|Checkbox|Date|Dropdown|Multi-select)$/

export async function expectFormFieldTypeLabel(page: Page, fieldNumber: number, typeLabel: FormFieldTypeMenuLabel) {
  await scrollFormFieldBuilderIntoView(page)
  await ensureFieldExpanded(page, fieldNumber)
  const card = formFieldBuilderCard(page, fieldNumber)
  await expect(card.getByRole('button', { name: FIELD_TYPE_TOGGLE_NAME })).toHaveText(typeLabel)
}

export async function expectFormFieldPlaceholderValue(page: Page, fieldNumber: number, placeholder: string) {
  await scrollFormFieldBuilderIntoView(page)
  await ensureFieldExpanded(page, fieldNumber)
  const card = formFieldBuilderCard(page, fieldNumber)
  await expect(card.getByRole('textbox', { name: 'Placeholder' })).toHaveValue(placeholder)
}

export async function expectFormFieldRequiredChecked(page: Page, fieldNumber: number, checked: boolean) {
  await scrollFormFieldBuilderIntoView(page)
  await ensureFieldExpanded(page, fieldNumber)
  const card = formFieldBuilderCard(page, fieldNumber)
  await expect(card.getByRole('checkbox', { name: 'Required' })).toBeChecked({ checked })
}

export async function selectFormFieldType(page: Page, fieldNumber: number, typeLabel: FormFieldTypeMenuLabel) {
  await scrollFormFieldBuilderIntoView(page)
  await ensureFieldExpanded(page, fieldNumber)
  const card = formFieldBuilderCard(page, fieldNumber)
  const toggle = card.getByRole('button', { name: FIELD_TYPE_TOGGLE_NAME })
  const currentLabel = (await toggle.innerText()).trim()
  if (currentLabel === typeLabel) {
    return
  }
  await toggle.scrollIntoViewIfNeeded()
  await toggle.click()
  if ((await toggle.getAttribute('aria-expanded')) !== 'true') {
    await toggle.click({ force: true })
  }
  const visibleOptions = page.getByRole('option', { name: typeLabel, exact: true }).filter({ visible: true })
  await expect(visibleOptions).toHaveCount(1, { timeout: 10_000 })
  await visibleOptions.click()
  await expect(toggle).toHaveText(typeLabel)
}

export async function removeFormField(page: Page, fieldNumber: number) {
  await scrollFormFieldBuilderIntoView(page)
  await formFieldBuilderCard(page, fieldNumber)
    .getByRole('button', { name: `Remove field ${fieldNumber}` })
    .click()
  const dialog = page.getByRole('dialog', { name: 'Remove field?' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Remove field' }).click()
  await expect(dialog).not.toBeVisible()
}

export async function reorderFormField(page: Page, fromFieldNumber: number, toFieldNumber: number) {
  await scrollFormFieldBuilderIntoView(page)
  const scope = formFieldBuilderScope(page)
  const source = scope.getByRole('button', { name: `Reorder field ${fromFieldNumber}` })
  const target = scope.getByRole('button', { name: `Reorder field ${toFieldNumber}` })
  await source.dragTo(target)
}

export async function fieldLabelValuesInOrder(page: Page): Promise<string[]> {
  await scrollFormFieldBuilderIntoView(page)
  return formFieldBuilderScope(page)
    .getByRole('textbox', { name: /Field label|Checkbox label/ })
    .evaluateAll((inputs) => inputs.map((input) => (input as HTMLInputElement).value))
}

export async function createFormPromptWorkflowWithBuilderOpen(
  page: Page,
  workflowName: string,
  nodeName = 'Intake Form'
): Promise<void> {
  await startWorkflowWithTrigger(page)
  await addFormPromptNodeWithSubmittedBranch(page, nodeName)
  await expect(page.getByRole('button', { name: 'Save workflow' })).toBeEnabled({ timeout: 15_000 })
  await saveWorkflow(page, workflowName)
  await openFormPromptNodeForEditing(page, nodeName)
  await scrollFormFieldBuilderIntoView(page)
}

export async function saveFormPromptNodeAndWorkflow(page: Page): Promise<void> {
  await saveAndCloseNodeForm(page, true)
  await closeNodeEditorPanel(page)
  await expect(page.getByRole('button', { name: 'Save workflow' })).toBeEnabled({ timeout: 15_000 })
  await clickSaveAndWait(page)
}

export type FormPromptDefinitionField = {
  type: string
  value_name: string
  label: string
  required?: boolean
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function parseFormPromptField(value: unknown): FormPromptDefinitionField | null {
  if (!isRecord(value)) {
    return null
  }
  const { type, value_name, label, required } = value
  if (typeof type !== 'string' || typeof value_name !== 'string' || typeof label !== 'string') {
    return null
  }
  if (required !== undefined && typeof required !== 'boolean') {
    return null
  }
  return required === undefined ? { type, value_name, label } : { type, value_name, label, required }
}

function isUnknownArray(value: unknown): value is unknown[] {
  return Array.isArray(value)
}

function workflowDefinitionNodes(workflow: unknown): unknown[] | null {
  if (!isRecord(workflow)) {
    return null
  }
  const version = workflow.version
  if (isRecord(version) && isRecord(version.workflow_definition)) {
    const nodes = version.workflow_definition.nodes
    if (isUnknownArray(nodes)) {
      return nodes
    }
  }
  const definition = workflow.definition
  if (isRecord(definition) && isUnknownArray(definition.nodes)) {
    return definition.nodes
  }
  return null
}

export async function readFormPromptDefinitionFromApi(
  page: Page,
  workflowId: string
): Promise<{ fields: FormPromptDefinitionField[] }> {
  const response = await apiRequest(page, 'get', `/workflows/${workflowId}`)
  const workflow: unknown = await response.json()
  const nodes = workflowDefinitionNodes(workflow)
  if (!nodes) {
    throw new Error('form_prompt workflow nodes not found on workflow')
  }
  const formNode = nodes.find((node) => isRecord(node) && node.type === 'form_prompt')
  if (!isRecord(formNode) || !isRecord(formNode.parameters)) {
    throw new Error('form_prompt node not found on workflow')
  }
  const formDefinition = formNode.parameters.form_definition
  if (!isRecord(formDefinition) || !Array.isArray(formDefinition.fields)) {
    throw new Error('form_prompt form_definition not found on workflow')
  }
  const fields: FormPromptDefinitionField[] = []
  for (const rawField of formDefinition.fields) {
    const field = parseFormPromptField(rawField)
    if (!field) {
      throw new Error('form_prompt form_definition fields failed validation')
    }
    fields.push(field)
  }
  return { fields }
}

export function workflowIdFromUrl(page: Page): string {
  const match = page.url().match(/workflow-builder\/([^/?]+)/)
  if (!match?.[1] || match[1] === 'new') {
    throw new Error(`Expected saved workflow URL, got ${page.url()}`)
  }
  return match[1]
}

export async function reloadBuilderAndReopenFormPrompt(page: Page, nodeName: string) {
  await page.reload()
  await waitForUIReady(page)
  await openFormPromptNodeForEditing(page, nodeName)
}

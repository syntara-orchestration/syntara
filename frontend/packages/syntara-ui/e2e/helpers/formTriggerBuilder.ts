/**
 * E2E helpers for form_trigger configuration in the workflow builder (SynFormFieldBuilder).
 */
import { expect, toAppUrl, type Page } from '../fixtures'
import { apiRequest } from '../utils/api'

import {
  type FormPromptDefinitionField,
  parseFormDefinitionFieldFromApi,
  scrollFormFieldBuilderIntoView,
} from './formFieldBuilder'
import { addFormTrigger, addScriptNode } from './v2-nodes'
import { clickSaveAndWait } from './workflow-save'
import {
  closeNodeEditorPanel,
  saveAndCloseNodeForm,
  saveWorkflow,
  selectProjectIfRequired,
  triggerLayout,
  waitForUIReady,
} from './workflows'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isUnknownArray(value: unknown): value is unknown[] {
  return Array.isArray(value)
}

function workflowDefinitionTriggers(workflow: unknown): unknown[] | null {
  if (!isRecord(workflow)) {
    return null
  }
  const version = workflow.version
  if (isRecord(version) && isRecord(version.workflow_definition)) {
    const triggers = version.workflow_definition.triggers
    if (isUnknownArray(triggers)) {
      return triggers
    }
  }
  const definition = workflow.definition
  if (isRecord(definition) && isUnknownArray(definition.triggers)) {
    return definition.triggers
  }
  return null
}

function readFormTriggerParameters(workflow: unknown): Record<string, unknown> {
  const triggers = workflowDefinitionTriggers(workflow)
  if (!triggers) {
    throw new Error('form_trigger workflow triggers not found on workflow')
  }
  const formTrigger = triggers.find((trigger) => isRecord(trigger) && trigger.type === 'form_trigger')
  if (!isRecord(formTrigger) || !isRecord(formTrigger.parameters)) {
    throw new Error('form_trigger trigger not found on workflow')
  }
  return formTrigger.parameters
}

/** Open the form_trigger node editor on the canvas. */
export async function openFormTriggerForEditing(page: Page, triggerName: string) {
  await triggerLayout(page)
  const node = page.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: triggerName })
  const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
  await expect(async () => {
    await expect(node).toBeVisible({ timeout: 5_000 })
    await node.dblclick({ force: true, timeout: 5_000 })
    await expect(nameInput).toHaveValue(triggerName, { timeout: 5_000 })
    await expect(page.locator('#form-trigger-form-fields')).toBeVisible({ timeout: 5_000 })
  }).toPass({ timeout: 30_000, intervals: [500, 1_000, 2_000] })
}

export async function createFormTriggerWorkflowWithBuilderOpen(
  page: Page,
  workflowName: string,
  triggerName = 'Start form'
): Promise<void> {
  await page.goto(toAppUrl('/workflow-builder/new'))
  await selectProjectIfRequired(page)
  await addFormTrigger(page, triggerName)
  await addScriptNode(page, 'Next step', 'print("ok")')
  await expect(page.getByRole('button', { name: 'Save workflow' })).toBeEnabled({ timeout: 15_000 })
  await saveWorkflow(page, workflowName)
  await openFormTriggerForEditing(page, triggerName)
  await scrollFormFieldBuilderIntoView(page, 'form_trigger')
}

export async function saveFormTriggerAndWorkflow(page: Page): Promise<void> {
  await saveAndCloseNodeForm(page, true)
  await closeNodeEditorPanel(page)
  await expect(page.getByRole('button', { name: 'Save workflow' })).toBeEnabled({ timeout: 15_000 })
  await clickSaveAndWait(page)
}

export async function readFormTriggerDefinitionFromApi(
  page: Page,
  workflowId: string
): Promise<{ fields: FormPromptDefinitionField[] }> {
  const response = await apiRequest(page, 'get', `/workflows/${workflowId}`)
  const workflow: unknown = await response.json()
  const parameters = readFormTriggerParameters(workflow)
  const formDefinition = parameters.form_definition
  if (!isRecord(formDefinition) || !Array.isArray(formDefinition.fields)) {
    throw new Error('form_trigger form_definition not found on workflow')
  }
  const fields: FormPromptDefinitionField[] = []
  for (const rawField of formDefinition.fields) {
    const field = parseFormDefinitionFieldFromApi(rawField)
    if (!field) {
      throw new Error('form_trigger form_definition fields failed validation')
    }
    fields.push(field)
  }
  return { fields }
}

export async function reloadBuilderAndReopenFormTrigger(page: Page, triggerName: string) {
  await page.reload()
  await waitForUIReady(page)
  await openFormTriggerForEditing(page, triggerName)
}

export { clickSaveAndWait }

/**
 * E2E helpers for form_trigger configuration in the workflow builder (SynFormFieldBuilder).
 */
import { TriggerTypeEnum } from '@syntara/contracts'

import { expect, toAppUrl, type Page } from '../fixtures'
import { isRealBackendE2e } from '../playwrightWebServerEnv'
import { apiRequest, ensureProject } from '../utils/api'

import { layoutCanvas } from './canvas-interaction'
import {
  type FormPromptDefinitionField,
  parseFormDefinitionFieldFromApi,
  scrollFormFieldBuilderIntoView,
} from './formFieldBuilder'
import { addFormTrigger, addScriptNode } from './v2-nodes'
import { clickSaveAndWait } from './workflow-save'
import {
  openNodeForEditing,
  saveAndCloseNodeForm,
  saveWorkflow,
  selectProjectIfRequired,
  waitForUIReady,
} from './workflows'

const FORM_TRIGGER_BUILDER_SAVE_TIMEOUT = isRealBackendE2e ? 60_000 : 30_000

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
  const formTrigger = triggers.find((trigger) => isRecord(trigger) && trigger.type === TriggerTypeEnum.FORM_TRIGGER)
  if (!isRecord(formTrigger) || !isRecord(formTrigger.parameters)) {
    throw new Error('form_trigger trigger not found on workflow')
  }
  return formTrigger.parameters
}

/** Open the form_trigger node editor on the canvas. */
export async function openFormTriggerForEditing(page: Page, triggerName: string) {
  const openTimeout = isRealBackendE2e ? 45_000 : 30_000
  await expect(async () => {
    await layoutCanvas(page)
    await waitForUIReady(page)
    await openNodeForEditing(page, triggerName)
    await expect(page.getByRole('heading', { name: 'Form fields', exact: true })).toBeVisible({ timeout: 5_000 })
  }).toPass({ timeout: openTimeout, intervals: [500, 1_000, 2_000] })
}

export async function createFormTriggerWorkflowWithBuilderOpen(
  page: Page,
  workflowName: string,
  triggerName = 'Start form'
): Promise<void> {
  await ensureProject(page)
  await page.goto(toAppUrl('/workflow-builder/new'))
  await selectProjectIfRequired(page)
  await addFormTrigger(page, triggerName)
  await addScriptNode(page, 'Next step', 'print("ok")')
  await expect(page.getByRole('button', { name: 'Save workflow' })).toBeEnabled({ timeout: 15_000 })
  await saveWorkflow(page, workflowName, { timeout: FORM_TRIGGER_BUILDER_SAVE_TIMEOUT })
  const triggerNode = page.getByRole('group').filter({ has: page.getByText(triggerName, { exact: true }) })
  await expect(triggerNode).toBeVisible({ timeout: isRealBackendE2e ? 30_000 : 15_000 })
  await waitForUIReady(page)
  await openFormTriggerForEditing(page, triggerName)
  await scrollFormFieldBuilderIntoView(page, 'form_trigger')
}

export async function saveFormTriggerAndWorkflow(page: Page): Promise<void> {
  await saveAndCloseNodeForm(page, true)
  await expect(page.getByRole('button', { name: 'Save workflow' })).toBeEnabled({ timeout: 15_000 })
  await clickSaveAndWait(page, { timeout: FORM_TRIGGER_BUILDER_SAVE_TIMEOUT })
}

const VALIDATION_BANNER_TITLE = /Saved with \d+ (warning|issue)|Verification failed — \d+ issue(s)? found/i

/** Builder canvas validation banner title after advisory save or verify. */
export function formTriggerValidationBannerTitle(page: Page) {
  return page.getByRole('heading', { name: VALIDATION_BANNER_TITLE })
}
/** Expand the verification validation alert on the builder canvas (scoped to main, not node panel alerts). */
export async function expandFormTriggerValidationBannerDetails(page: Page) {
  await expect(page.getByText(/Verification failed/)).toBeVisible({ timeout: 15_000 })
  const details = page.getByRole('main').getByRole('button', { name: /alert details/i })
  await expect(async () => {
    await expect(details).toBeVisible({ timeout: 3_000 })
    await details.click()
  }).toPass({ timeout: 15_000, intervals: [500, 1_000] })
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
  const reloadTimeout = isRealBackendE2e ? 90_000 : 60_000
  await expect(async () => {
    await page.reload()
    await waitForUIReady(page)
    await openFormTriggerForEditing(page, triggerName)
  }).toPass({ timeout: reloadTimeout, intervals: [1_000, 2_000, 3_000] })
}

export { clickSaveAndWait }

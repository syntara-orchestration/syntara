import type { WorkflowAPI } from '@syntara/contracts'

import { workflowFetchClient } from '../../client'
import { activitiesReferenceTrigger } from '../builder/utils/triggerReferenceCheck'

import {
  formTriggerRequiresInputCollection,
  isFormTriggerType,
  readFormTriggerPresentation,
  type FormTriggerPresentation,
} from './formTrigger/formTriggerRunUtils'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

type TriggerLike = {
  id?: string
  name?: string
  type?: string
  parameters?: {
    input_schema?: Record<string, unknown>
    form_definition?: unknown
    message?: string | null
    submit_label?: string | null
    success_message?: string | null
    css_override?: string | null
  }
}

export type WorkflowRunTrigger = {
  triggerNodeId: string
  triggerName: string
  triggerType?: string
  inputSchema?: Record<string, unknown>
  hasTriggerReferences: boolean
  formTrigger?: FormTriggerPresentation
}

function isTriggerLike(value: unknown): value is TriggerLike {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function extractTriggers(definition: unknown): TriggerLike[] | undefined {
  if (!definition || typeof definition !== 'object') return undefined
  const triggers = (definition as { triggers?: unknown }).triggers
  if (!Array.isArray(triggers)) return undefined
  return triggers.filter(isTriggerLike)
}

type ActivityLike = { parameters?: Record<string, unknown> }

function extractActivities(definition: unknown): ActivityLike[] {
  if (!definition || typeof definition !== 'object') return []
  const nodes = (definition as { nodes?: unknown }).nodes
  if (!Array.isArray(nodes)) return []
  return nodes.filter((n): n is ActivityLike => typeof n === 'object' && n !== null)
}

function buildRunTrigger(trigger: TriggerLike, triggers: TriggerLike[], definition: unknown): WorkflowRunTrigger {
  const activities = extractActivities(definition)
  const triggerNodeIds = triggers.flatMap((t) => (t.id ? [t.id] : []))
  const inputSchema = trigger.parameters?.input_schema
  if (!trigger.id) {
    throw new Error('Trigger is missing id')
  }
  const formTrigger = isFormTriggerType(trigger.type) ? readFormTriggerPresentation(trigger.parameters) : undefined

  return {
    triggerNodeId: trigger.id,
    triggerName: trigger.name ?? 'Trigger',
    triggerType: trigger.type,
    inputSchema: inputSchema && typeof inputSchema === 'object' ? inputSchema : undefined,
    hasTriggerReferences: activitiesReferenceTrigger(activities, triggerNodeIds),
    formTrigger,
  }
}

type LoadedWorkflowRunDefinition = {
  definition: unknown
  triggersWithId: (TriggerLike & { id: string })[]
}

async function loadWorkflowRunDefinition(workflow: Workflow): Promise<LoadedWorkflowRunDefinition | null> {
  if (!workflow.id) return null

  const { data: detail, error } = await workflowFetchClient.GET('/workflows/{workflow_id}', {
    params: { path: { workflow_id: workflow.id } },
  })
  if (error || !detail) return null

  const publishedVersionNumber = workflow.published_version_number ?? detail.published_version_number
  const currentVersionNumber = detail.current_version
  let definition = detail.version?.workflow_definition
  let triggers = extractTriggers(definition)

  if (
    publishedVersionNumber != null &&
    currentVersionNumber != null &&
    publishedVersionNumber !== currentVersionNumber
  ) {
    const { data: publishedVersion, error: versionError } = await workflowFetchClient.GET(
      '/workflows/{workflow_id}/versions/{version}',
      {
        params: { path: { workflow_id: workflow.id, version: publishedVersionNumber } },
      }
    )
    if (versionError || !publishedVersion?.workflow_definition) {
      throw new Error('Could not load the published workflow version. Try again or republish the workflow.')
    }
    definition = publishedVersion.workflow_definition
    triggers = extractTriggers(definition) ?? triggers
  }

  const triggersWithId = (triggers ?? []).filter((t): t is TriggerLike & { id: string } => Boolean(t.id))
  return { definition, triggersWithId }
}

export type WorkflowListRunTriggerResolution =
  { kind: 'single'; trigger: WorkflowRunTrigger } | { kind: 'chooseFormStep'; triggers: WorkflowRunTrigger[] }

function listFormStepsRequiringInput(
  triggersWithId: (TriggerLike & { id: string })[],
  definition: unknown
): WorkflowRunTrigger[] {
  return triggersWithId
    .filter((trigger) => isFormTriggerType(trigger.type))
    .map((trigger) => buildRunTrigger(trigger, triggersWithId, definition))
    .filter((trigger) => formTriggerRequiresInputCollection(trigger.formTrigger))
}

/**
 * Resolve how to start a workflow run from the workflows list.
 * When multiple form steps require input, the caller must show a form-step picker.
 */
export async function resolveWorkflowListRunTrigger(
  workflow: Workflow
): Promise<WorkflowListRunTriggerResolution | null> {
  const loaded = await loadWorkflowRunDefinition(workflow)
  if (!loaded) return null

  const { definition, triggersWithId } = loaded
  if (triggersWithId.length === 0) return null

  const formStepsRequiringInput = listFormStepsRequiringInput(triggersWithId, definition)
  if (formStepsRequiringInput.length >= 2) {
    return { kind: 'chooseFormStep', triggers: formStepsRequiringInput }
  }

  const trigger = triggersWithId.find((t) => isFormTriggerType(t.type)) ?? triggersWithId[0]
  if (!trigger?.id) return null

  return { kind: 'single', trigger: buildRunTrigger(trigger, triggersWithId, definition) }
}

/**
 * Resolve the first trigger from the workflow's published definition for a list-page run.
 * Prefers the published version when it differs from the current draft.
 */
const MULTIPLE_FORM_STEPS_RUN_ERROR =
  'This workflow has multiple form steps. Run it from the workflows list and choose which form step to run.'

export async function resolveWorkflowRunTrigger(workflow: Workflow): Promise<WorkflowRunTrigger | null> {
  const resolution = await resolveWorkflowListRunTrigger(workflow)
  if (!resolution) return null
  if (resolution.kind === 'chooseFormStep') {
    throw new Error(MULTIPLE_FORM_STEPS_RUN_ERROR)
  }
  return resolution.trigger
}

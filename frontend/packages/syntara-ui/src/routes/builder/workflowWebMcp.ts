import { ActivityTypeEnum, EdgeHandleEnum, type Activity } from '@syntara/contracts'

import { createManualTrigger } from '../../stores/triggerFactories'
import type { WorkflowDefinition } from '../../stores/workflowStoreTypes'
import { generateActivityId } from '../../utils/generateUUID'

import type { EdgeConnection } from './types/edge'
import { validateWorkflow } from './utils/validation'
import { validateMinimumWorkflow } from './utils/validation/rules/validateMinimumWorkflow'

export const WEBMCP_WORKFLOW_STEP_TYPES = [
  ActivityTypeEnum.AGENTIC,
  ActivityTypeEnum.APPROVAL,
  ActivityTypeEnum.AAP_JOB_TEMPLATE,
  ActivityTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE,
  ActivityTypeEnum.HTTP_REQUEST,
] as const

const FORBIDDEN_PARAMETER_KEYS = new Set(['__proto__', 'prototype', 'constructor'])
const SECRET_PARAMETER_KEY = /password|secret|token|authorization|api[_-]?key|cookie/i
const MAX_STEP_COUNT = 10
const MAX_PARAMETER_LENGTH = 50_000

type DraftStepInput = {
  type: (typeof WEBMCP_WORKFLOW_STEP_TYPES)[number]
  name: string
  parameters?: Record<string, unknown>
}

type DraftInput = {
  name: string
  description: string
  steps: DraftStepInput[]
}

export type WorkflowDraftBuildResult =
  | { ok: true; workflow: WorkflowDefinition; edges: EdgeConnection[]; name: string; description: string }
  | { ok: false; message: string }

export type WorkflowValidationSummary = {
  errors: string[]
  warnings: string[]
  readyToRun: boolean
}

function isRecord(value: unknown): value is Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const prototype = Object.getPrototypeOf(value) as unknown
  return prototype === Object.prototype || prototype === null
}

function isControlCodePoint(codePoint: number): boolean {
  return (
    codePoint <= 0x1f ||
    (codePoint >= 0x7f && codePoint <= 0x9f) ||
    (codePoint >= 0x200e && codePoint <= 0x200f) ||
    (codePoint >= 0x202a && codePoint <= 0x202e) ||
    (codePoint >= 0x2066 && codePoint <= 0x2069)
  )
}

function stripControlCharacters(value: string): string {
  return Array.from(value)
    .filter((character) => {
      const codePoint = character.codePointAt(0)
      return codePoint !== undefined && !isControlCodePoint(codePoint)
    })
    .join('')
}

function cleanText(value: unknown, label: string, maxLength: number): string {
  if (typeof value !== 'string') throw new Error(`${label} must be text.`)
  const cleaned = stripControlCharacters(value).trim()
  if (cleaned.length === 0) throw new Error(`${label} is required.`)
  if (cleaned.length > maxLength) throw new Error(`${label} must be ${maxLength} characters or fewer.`)
  return cleaned
}

function validateJsonArray(value: unknown[], path: string, depth: number, ancestors: WeakSet<object>): void {
  if (value.length > 100) throw new Error(`${path} has too many items.`)
  if (ancestors.has(value)) throw new Error(`${path} must not contain circular values.`)
  ancestors.add(value)
  value.forEach((item, index) => validateJsonValue(item, `${path}[${index}]`, depth + 1, ancestors))
  ancestors.delete(value)
}

function validateJsonObject(
  value: Record<string, unknown>,
  path: string,
  depth: number,
  ancestors: WeakSet<object>
): void {
  if (ancestors.has(value)) throw new Error(`${path} must not contain circular values.`)
  ancestors.add(value)
  if (typeof value.key === 'string' && SECRET_PARAMETER_KEY.test(value.key)) {
    throw new Error(`${path}.${value.key} may contain a secret. Use a Syntara credential reference instead.`)
  }
  for (const [key, item] of Object.entries(value)) {
    if (FORBIDDEN_PARAMETER_KEYS.has(key)) throw new Error(`${path} contains a reserved property.`)
    if (SECRET_PARAMETER_KEY.test(key)) {
      throw new Error(`${path}.${key} may contain a secret. Use a Syntara credential reference instead.`)
    }
    validateJsonValue(item, `${path}.${key}`, depth + 1, ancestors)
  }
  ancestors.delete(value)
}

function validateJsonValue(value: unknown, path: string, depth = 0, ancestors = new WeakSet<object>()): void {
  if (depth > 10) throw new Error(`${path} is nested too deeply.`)
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return
  if (typeof value === 'number' && Number.isFinite(value)) return
  if (Array.isArray(value)) return validateJsonArray(value, path, depth, ancestors)
  if (!isRecord(value)) throw new Error(`${path} must contain JSON values only.`)
  validateJsonObject(value, path, depth, ancestors)
}

function copyParameterObject(value: unknown, path: string): Record<string, unknown> {
  if (!isRecord(value)) throw new Error(`${path} must be an object.`)
  validateJsonValue(value, path)
  return structuredClone(value)
}

function parseDraftInput(input: unknown): DraftInput {
  if (!isRecord(input)) throw new Error('Provide a workflow name, description, and steps.')

  const name = cleanText(input.name, 'Workflow name', 255)
  if (typeof input.description !== 'string') throw new Error('Workflow description must be text.')
  const description = stripControlCharacters(input.description).trim()
  if (description.length > 1024) throw new Error('Workflow description must be 1024 characters or fewer.')

  if (!Array.isArray(input.steps) || input.steps.length === 0 || input.steps.length > MAX_STEP_COUNT) {
    throw new Error(`Provide between 1 and ${MAX_STEP_COUNT} workflow steps.`)
  }

  const steps = input.steps.map((step, index): DraftStepInput => {
    if (!isRecord(step)) throw new Error(`Step ${index + 1} must be an object.`)
    const type = step.type
    if (typeof type !== 'string' || !WEBMCP_WORKFLOW_STEP_TYPES.includes(type as DraftStepInput['type'])) {
      throw new Error(`Step ${index + 1} has an unsupported type.`)
    }
    const stepName = cleanText(step.name, `Step ${index + 1} name`, 255)
    const parameters =
      step.parameters === undefined ? {} : copyParameterObject(step.parameters, `Step ${index + 1} parameters`)
    return { type: type as DraftStepInput['type'], name: stepName, parameters }
  })

  const totalLength = JSON.stringify(steps).length
  if (totalLength > MAX_PARAMETER_LENGTH) throw new Error('Workflow step configuration is too large.')

  return { name, description, steps }
}

export function buildWorkflowDraft(
  input: unknown,
  currentWorkflow: WorkflowDefinition | null,
  currentEdges: EdgeConnection[]
): WorkflowDraftBuildResult {
  if (!currentWorkflow) return { ok: false, message: 'The workflow builder is still loading. Try again shortly.' }
  const activities = currentWorkflow.workflow.activities
  if (activities.length > 0 || (currentWorkflow.triggers?.length ?? 0) > 0 || currentEdges.length > 0) {
    return { ok: false, message: 'Draft creation is available on an empty workflow builder.' }
  }

  try {
    const draft = parseDraftInput(input)
    const trigger = createManualTrigger(generateActivityId('trigger'), false, 'Manual Trigger')
    const newActivities: Activity[] = draft.steps.map((step) => ({
      id: generateActivityId(step.type),
      type: step.type,
      name: step.name,
      parameters: step.parameters ?? {},
    }))

    const edges: EdgeConnection[] = newActivities.map((activity, index) => {
      const previousActivity = index === 0 ? trigger : newActivities[index - 1]
      if (!previousActivity) throw new Error('The workflow graph could not be connected.')
      const source = index === 0 ? 'trigger-0' : previousActivity.id
      const sourceHandle =
        previousActivity.type === ActivityTypeEnum.APPROVAL ? EdgeHandleEnum.APPROVED : EdgeHandleEnum.SOURCE
      return {
        id: generateActivityId('edge'),
        source,
        target: activity.id,
        sourceHandle,
        targetHandle: EdgeHandleEnum.TARGET,
      }
    })

    return {
      ok: true,
      name: draft.name,
      description: draft.description,
      workflow: {
        ...currentWorkflow,
        name: draft.name,
        description: draft.description,
        triggers: [trigger],
        workflow: { ...currentWorkflow.workflow, activities: newActivities },
      },
      edges,
    }
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : 'The workflow draft could not be created.',
    }
  }
}

export function validateWorkflowDraft(
  activities: Activity[],
  edges: EdgeConnection[],
  triggers: Activity[]
): WorkflowValidationSummary {
  const minimumErrors = validateMinimumWorkflow(activities, edges, triggers)
  const structural = validateWorkflow(activities, edges, { triggers })
  const errors = [...minimumErrors, ...structural.errors].map((finding) => finding.message)
  const warnings = structural.warnings.map((finding) => finding.message)
  return { errors, warnings, readyToRun: errors.length === 0 }
}

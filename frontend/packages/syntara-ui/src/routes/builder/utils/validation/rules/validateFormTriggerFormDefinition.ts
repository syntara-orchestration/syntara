import { TriggerTypeEnum, type Activity } from '@syntara/contracts'

import { safeParseFormDefinition } from '../../../../../forms'
import type { EdgeConnection } from '../../../types/edge'
import type { ValidationContext, ValidationError } from '../types'

const FORM_TRIGGER_PARAMETER_KEYS = [
  'form_definition',
  'message',
  'submit_label',
  'success_message',
  'css_override',
] as const

type DraftFormField = { type?: string; value_name?: string; options?: { source?: string } }

function hasFormTriggerParameterKeys(parameters: Record<string, unknown> | undefined): boolean {
  if (!parameters) return false
  return FORM_TRIGGER_PARAMETER_KEYS.some((key) => key in parameters)
}

function formTriggerDynamicOptionErrors(
  triggerId: string,
  nodeName: string,
  fields: ReadonlyArray<DraftFormField>
): ValidationError[] {
  const errors: ValidationError[] = []
  for (const field of fields) {
    if (field.type !== 'dropdown' && field.type !== 'multi_select') continue
    if (field.options?.source !== 'dynamic') continue
    const fieldName = field.value_name ?? 'field'
    errors.push({
      id: `form-trigger-dynamic-options-${triggerId}-${fieldName}`,
      severity: 'error',
      rule: 'form-trigger-dynamic-options',
      message: `Form trigger "${nodeName}": field "${fieldName}" uses dynamic options, which are not supported on a form trigger`,
      nodeId: triggerId,
    })
  }
  return errors
}

function readDraftFormFields(raw: unknown): DraftFormField[] | undefined {
  const fields = (raw as { fields?: DraftFormField[] } | undefined)?.fields
  return Array.isArray(fields) && fields.length > 0 ? fields : undefined
}

function formTriggerDefinitionErrors(trigger: Activity): ValidationError[] {
  const nodeName = trigger.name ?? trigger.id
  const raw = (trigger.parameters as { form_definition?: unknown } | undefined)?.form_definition
  const parsed = safeParseFormDefinition(raw)

  if (parsed.success && parsed.data.fields.length > 0) {
    return formTriggerDynamicOptionErrors(trigger.id, nodeName, parsed.data.fields)
  }

  const draftFields = readDraftFormFields(raw)
  const dynamicErrors = draftFields
    ? formTriggerDynamicOptionErrors(trigger.id, nodeName, draftFields)
    : []

  const detail = parsed.success
    ? 'Add at least one form field'
    : (parsed.errors[0]?.message ?? 'Form definition is invalid')

  return [
    ...dynamicErrors,
    {
      id: `form-trigger-definition-${trigger.id}`,
      severity: 'error',
      rule: 'form-trigger-form-definition',
      message: `Form trigger "${nodeName}" has an invalid form definition: ${detail}`,
      nodeId: trigger.id,
    },
  ]
}

function validateSingleFormTrigger(trigger: Activity): ValidationError[] {
  const nodeName = trigger.name ?? trigger.id
  const parameters = trigger.parameters as Record<string, unknown> | undefined

  if (trigger.type === TriggerTypeEnum.MANUAL_TRIGGER && hasFormTriggerParameterKeys(parameters)) {
    return [
      {
        id: `form-trigger-type-mismatch-${trigger.id}`,
        severity: 'error',
        rule: 'form-trigger-type-mismatch',
        message:
          `Trigger "${nodeName}" uses form trigger settings but its type is manual_trigger. ` +
          'Remove the trigger and add a Form trigger from the palette, or clear the form fields and use a manual trigger.',
        nodeId: trigger.id,
      },
    ]
  }

  if (trigger.type !== TriggerTypeEnum.FORM_TRIGGER) {
    return []
  }

  const parsed = safeParseFormDefinition(
    (trigger.parameters as { form_definition?: unknown } | undefined)?.form_definition
  )
  if (parsed.success && parsed.data.fields.length > 0) {
    return formTriggerDynamicOptionErrors(trigger.id, nodeName, parsed.data.fields)
  }

  return formTriggerDefinitionErrors(trigger)
}

export function validateFormTriggerFormDefinition(
  activities: Activity[],
  edges: EdgeConnection[],
  context?: ValidationContext
): ValidationError[] {
  if (activities.length === 0 && edges.length === 0 && context === undefined) {
    return []
  }

  const triggers = context?.triggers ?? []
  return triggers.flatMap((trigger) => validateSingleFormTrigger(trigger))
}

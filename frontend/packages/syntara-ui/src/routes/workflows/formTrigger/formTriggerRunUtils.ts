import { TriggerTypeEnum, type FormDefinition } from '@syntara/contracts'

import { safeParseFormDefinition } from '../../../forms'
import { hasNonEmptyInputSchema } from '../../builder/utils/triggerReferenceCheck'
import type { WorkflowRunTrigger } from '../resolveWorkflowRunTrigger'

export type FormTriggerPresentation = {
  definition: FormDefinition
  message?: string | null
  submitLabel?: string | null
  successMessage?: string | null
  cssOverride?: string | null
}

type TriggerParametersLike = {
  form_definition?: unknown
  message?: string | null
  submit_label?: string | null
  success_message?: string | null
  css_override?: string | null
  input_schema?: Record<string, unknown>
}

export function isFormTriggerType(triggerType?: string): boolean {
  return triggerType === TriggerTypeEnum.FORM_TRIGGER
}

export function readFormTriggerPresentation(parameters?: TriggerParametersLike): FormTriggerPresentation | undefined {
  if (!parameters?.form_definition) {
    return undefined
  }

  const parsed = safeParseFormDefinition(parameters.form_definition)
  if (!parsed.success) {
    return undefined
  }

  return {
    definition: parsed.data,
    message: parameters.message,
    submitLabel: parameters.submit_label,
    successMessage: parameters.success_message,
    cssOverride: parameters.css_override,
  }
}

export function formTriggerRequiresInputCollection(formTrigger?: FormTriggerPresentation): boolean {
  return Boolean(formTrigger && formTrigger.definition.fields.length > 0)
}

export function workflowRunTriggerRequiresInputCollection(trigger: WorkflowRunTrigger): boolean {
  if (isFormTriggerType(trigger.triggerType)) {
    return formTriggerRequiresInputCollection(trigger.formTrigger)
  }
  if (trigger.hasTriggerReferences) {
    return true
  }
  if (hasNonEmptyInputSchema(trigger.inputSchema)) {
    return true
  }
  return false
}

/** Form-trigger runs skip the manual "Run workflow?" confirmation and open the form when applicable. */
export function workflowRunSkipsManualRunConfirmation(trigger: WorkflowRunTrigger): boolean {
  return isFormTriggerType(trigger.triggerType) && Boolean(trigger.formTrigger)
}

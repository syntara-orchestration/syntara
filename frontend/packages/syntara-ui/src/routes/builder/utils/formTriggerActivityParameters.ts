import type { FormDefinition } from '@syntara/contracts'

import { serializeFormDefinitionForStorage } from '../../../forms'

export type FormTriggerActivityParameterInput = {
  form_definition: FormDefinition
  message?: string | null
  submit_label?: string | null
  success_message?: string | null
  css_override?: string | null
}

function appendOptionalString(target: Record<string, unknown>, key: string, value: string | null | undefined): void {
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (trimmed !== '') {
      target[key] = trimmed
    }
  }
}

export function buildFormTriggerActivityParameters(input: FormTriggerActivityParameterInput): Record<string, unknown> {
  const result: Record<string, unknown> = {
    form_definition: serializeFormDefinitionForStorage(input.form_definition),
  }
  appendOptionalString(result, 'message', input.message)
  appendOptionalString(result, 'submit_label', input.submit_label)
  appendOptionalString(result, 'success_message', input.success_message)
  appendOptionalString(result, 'css_override', input.css_override)
  return result
}

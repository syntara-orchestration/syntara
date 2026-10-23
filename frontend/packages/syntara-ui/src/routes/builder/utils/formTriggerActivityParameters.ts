import type { FormDefinition } from '@syntara/contracts'

import { prepareFormDefinitionForCommit, safeParseFormDefinition } from '../../../forms'

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
  const preparedDefinition = prepareFormDefinitionForCommit(input.form_definition)
  const parsedDefinition = safeParseFormDefinition(preparedDefinition)
  if (!parsedDefinition.success) {
    const detail = parsedDefinition.errors[0]?.message ?? 'Form definition is invalid'
    throw new Error(detail)
  }

  for (const field of parsedDefinition.data.fields) {
    const options = field.type === 'dropdown' || field.type === 'multi_select' ? field.options : null
    if (options?.source === 'dynamic') {
      throw new Error(`Field "${field.value_name}": dynamic options are not supported on a form trigger`)
    }
  }

  const result: Record<string, unknown> = {
    form_definition: parsedDefinition.data,
  }
  appendOptionalString(result, 'message', input.message)
  appendOptionalString(result, 'submit_label', input.submit_label)
  appendOptionalString(result, 'success_message', input.success_message)
  appendOptionalString(result, 'css_override', input.css_override)
  return result
}

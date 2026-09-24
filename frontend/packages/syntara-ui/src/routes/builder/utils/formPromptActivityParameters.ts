import type { FormDefinition } from '@syntara/contracts'

export type FormPromptActivityParameterInput = {
  form_definition: FormDefinition
  message?: string | null
  responder_users?: string[]
  responder_groups?: string[]
  response_window?: number | null
  fallback_decision?: 'submit' | 'fallback' | null
  fallback_behavior?: 'fail' | 'fallback'
  submit_label?: string | null
  success_message?: string | null
  timezone?: string | null
  css_override?: string | null
}

export function buildFormPromptActivityParameters(input: FormPromptActivityParameterInput): Record<string, unknown> {
  const {
    form_definition,
    message,
    responder_users,
    responder_groups,
    response_window,
    fallback_decision,
    fallback_behavior,
    submit_label,
    success_message,
    timezone,
    css_override,
  } = input

  return {
    form_definition,
    ...(message != null && message !== '' && { message }),
    ...(fallback_decision !== undefined && fallback_decision !== null && { fallback_decision }),
    ...(fallback_behavior !== undefined && { fallback_behavior }),
    ...(response_window !== undefined && response_window !== null && { response_window }),
    ...(responder_users !== undefined && responder_users.length > 0 && { responder_users }),
    ...(responder_groups !== undefined && responder_groups.length > 0 && { responder_groups }),
    ...(submit_label != null && submit_label !== '' && { submit_label }),
    ...(success_message != null && success_message !== '' && { success_message }),
    ...(timezone != null && timezone !== '' && { timezone }),
    ...(css_override != null && css_override !== '' && { css_override }),
  }
}

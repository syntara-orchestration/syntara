import type { FormDefinition } from '@syntara/contracts'

import { prepareFormDefinitionForCommit, safeParseFormDefinition } from '../../../forms'

export type FormPromptActivityParameterInput = {
  form_definition: FormDefinition
  message?: string | null
  responder_users?: string[]
  responder_groups?: string[]
  response_window?: number | null
  fallback_decision?: 'submit' | 'fallback' | null
  submit_label?: string | null
  success_message?: string | null
  timezone?: string | null
  css_override?: string | null
}

type OptionalFormPromptField = {
  key: string
  read: (input: FormPromptActivityParameterInput) => unknown
  include: (value: unknown) => boolean
}

const OPTIONAL_FORM_PROMPT_FIELDS: OptionalFormPromptField[] = [
  {
    key: 'message',
    read: (input) => input.message,
    include: (value) => typeof value === 'string' && value !== '',
  },
  {
    key: 'fallback_decision',
    read: (input) => input.fallback_decision,
    include: (value) => value !== undefined && value !== null,
  },
  {
    key: 'response_window',
    read: (input) => input.response_window,
    include: (value) => value !== undefined && value !== null,
  },
  {
    key: 'responder_users',
    read: (input) => input.responder_users,
    include: (value) => Array.isArray(value) && value.length > 0,
  },
  {
    key: 'responder_groups',
    read: (input) => input.responder_groups,
    include: (value) => Array.isArray(value) && value.length > 0,
  },
  {
    key: 'submit_label',
    read: (input) => input.submit_label,
    include: (value) => typeof value === 'string' && value !== '',
  },
  {
    key: 'success_message',
    read: (input) => input.success_message,
    include: (value) => typeof value === 'string' && value !== '',
  },
  {
    key: 'timezone',
    read: (input) => input.timezone,
    include: (value) => typeof value === 'string' && value !== '',
  },
  {
    key: 'css_override',
    read: (input) => input.css_override,
    include: (value) => typeof value === 'string' && value !== '',
  },
]

function appendOptionalFormPromptFields(
  target: Record<string, unknown>,
  input: FormPromptActivityParameterInput
): void {
  for (const field of OPTIONAL_FORM_PROMPT_FIELDS) {
    const value = field.read(input)
    if (field.include(value)) {
      target[field.key] = value
    }
  }
}

export function buildFormPromptActivityParameters(input: FormPromptActivityParameterInput): Record<string, unknown> {
  const preparedDefinition = prepareFormDefinitionForCommit(input.form_definition)
  const parsedDefinition = safeParseFormDefinition(preparedDefinition)
  if (!parsedDefinition.success) {
    const detail = parsedDefinition.errors[0]?.message ?? 'Form definition is invalid'
    throw new Error(detail)
  }

  const result: Record<string, unknown> = {
    form_definition: parsedDefinition.data,
  }
  appendOptionalFormPromptFields(result, input)
  return result
}

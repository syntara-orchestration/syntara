import type { FormDefinition } from '@syntara/contracts'

import type { FormFieldErrorCode, FormFieldValidationError } from './formValidationErrors'

const FORM_VALIDATION_DETAIL_PREFIX = 'Form validation failed: '

function inferFieldErrorCode(message: string): FormFieldErrorCode {
  if (message === 'This field is required') {
    return 'required'
  }
  if (message.includes('Unknown field')) {
    return 'unknown_field'
  }
  if (message.includes('option list')) {
    return 'not_in_options'
  }
  if (message.includes('valid number') || message.includes('Must be a')) {
    return 'type'
  }
  if (message.includes('email')) {
    return 'invalid_format'
  }
  return 'type'
}

/**
 * Parse RFC 9457 `detail` from a form submission validation response into field errors.
 */
export function parseFormValidationProblemDetail(
  detail: string,
  definition?: FormDefinition
): FormFieldValidationError[] {
  if (!detail.startsWith(FORM_VALIDATION_DETAIL_PREFIX)) {
    return []
  }

  const remainder = detail.slice(FORM_VALIDATION_DETAIL_PREFIX.length).trim()
  if (!remainder) {
    return []
  }

  const labelByField = new Map(definition?.fields.map((field) => [field.value_name, field.label]) ?? [])

  return remainder.split('; ').map((segment) => {
    const trimmed = segment.trim()
    const separatorIndex = trimmed.indexOf(': ')
    if (separatorIndex === -1) {
      return {
        field: trimmed,
        label: trimmed,
        code: 'type',
        message: trimmed,
      }
    }

    const field = trimmed.slice(0, separatorIndex)
    const message = trimmed.slice(separatorIndex + 2)
    return {
      field,
      label: labelByField.get(field) ?? field,
      code: inferFieldErrorCode(message),
      message,
    }
  })
}

export function isFormValidationProblemDetail(detail: string): boolean {
  return detail.startsWith(FORM_VALIDATION_DETAIL_PREFIX)
}

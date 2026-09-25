import type { FormDefinition } from '@syntara/contracts'

import { FormFieldTypeEnum, type FormSubmissionInput } from '../../../forms'

/**
 * Builds react-hook-form default values from a form definition and optional overrides.
 */
export function buildDefaultValues(definition: FormDefinition, overrides?: FormSubmissionInput): FormSubmissionInput {
  const values: FormSubmissionInput = {}

  for (const field of definition.fields) {
    const override = overrides?.[field.value_name]
    if (override !== undefined) {
      values[field.value_name] = override
      continue
    }

    if (field.default != null) {
      values[field.value_name] = field.default
      continue
    }

    if (field.type === FormFieldTypeEnum.CHECKBOX) {
      values[field.value_name] = false
      continue
    }

    if (field.type === FormFieldTypeEnum.MULTI_SELECT) {
      values[field.value_name] = []
      continue
    }

    if (field.type === FormFieldTypeEnum.NUMBER) {
      values[field.value_name] = ''
      continue
    }

    values[field.value_name] = ''
  }

  return values
}

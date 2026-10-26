import type { FormDefinitionFieldServerError } from '../../../components/forms/formFieldBuilder/formDefinitionFieldServerError'

export type { FormDefinitionFieldServerError }

const PARAMETER_PREFIX = 'parameters.'
const FIELDS_DOT_PREFIX = 'form_definition.fields.'
const FIELDS_BRACKET_PATTERN = /^form_definition\.fields\[(\d+)\](?:\.(.+))?$/

function parseFieldIndexAndSubPath(relative: string): { fieldIndex: number; subPath: string } | null {
  const bracketMatch = FIELDS_BRACKET_PATTERN.exec(relative)
  if (bracketMatch) {
    const fieldIndex = Number(bracketMatch[1])
    if (Number.isNaN(fieldIndex)) return null
    return { fieldIndex, subPath: bracketMatch[2] ?? '' }
  }

  if (!relative.startsWith(FIELDS_DOT_PREFIX)) {
    return null
  }

  const remainder = relative.slice(FIELDS_DOT_PREFIX.length)
  const dotIndex = remainder.indexOf('.')
  if (dotIndex === -1) {
    const fieldIndex = Number(remainder)
    return Number.isNaN(fieldIndex) ? null : { fieldIndex, subPath: '' }
  }

  const fieldIndex = Number(remainder.slice(0, dotIndex))
  if (Number.isNaN(fieldIndex)) return null
  return { fieldIndex, subPath: remainder.slice(dotIndex + 1) }
}

/** Parse API `field_path` values that point at a form definition field row. */
export function parseFormTriggerFormDefinitionFieldPath(
  fieldPath: string | null | undefined,
  message: string
): FormDefinitionFieldServerError | null {
  if (!fieldPath?.startsWith(PARAMETER_PREFIX)) {
    return null
  }
  const relative = fieldPath.slice(PARAMETER_PREFIX.length)
  const parsed = parseFieldIndexAndSubPath(relative)
  if (!parsed) {
    return null
  }
  return { ...parsed, message }
}

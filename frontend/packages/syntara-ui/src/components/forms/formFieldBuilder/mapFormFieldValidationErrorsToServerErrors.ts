import {
  humanizeFormDefinitionIssueMessage,
  parseFormDefinitionErrorLocation,
  type FormFieldValidationError,
} from '../../../forms'

import type { FormDefinitionFieldServerError } from './formDefinitionFieldServerError'

function subPathFromLocation(location: NonNullable<ReturnType<typeof parseFormDefinitionErrorLocation>>): string {
  if (location.optionIndex === undefined) {
    return location.propertyKey ?? ''
  }
  const property = location.propertyKey ?? ''
  return property ? `options.values.${location.optionIndex}.${property}` : `options.values.${location.optionIndex}`
}

/** Maps {@link safeParseFormDefinition} findings to builder row errors while banner verify/save errors are active. */
export function mapFormFieldValidationErrorsToServerErrors(
  errors: ReadonlyArray<FormFieldValidationError>
): FormDefinitionFieldServerError[] {
  const result: FormDefinitionFieldServerError[] = []

  for (const error of errors) {
    const location = parseFormDefinitionErrorLocation(error.field)
    if (!location) {
      continue
    }

    result.push({
      fieldIndex: location.fieldIndex,
      subPath: subPathFromLocation(location),
      message: humanizeFormDefinitionIssueMessage(error.message, error.field, { includeFieldLocation: false }),
    })
  }

  return result
}

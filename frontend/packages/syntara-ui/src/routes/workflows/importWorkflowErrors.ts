import { getErrorCode, isValidationError } from '../../utils/apiErrors'

export const IMPORT_NAME_CONFLICT_MESSAGE = 'Name conflict: A workflow with this name already exists in the project.'

export const IMPORT_INVALID_FORMAT_MESSAGE =
  'Invalid format: The imported file has an invalid workflow format. Ensure it was exported from a compatible version.'

export const IMPORT_DEFAULT_ERROR_MESSAGE =
  'Could not import this workflow. Try again, or contact your administrator if this continues.'

function isInvalidFormatApiError(error: unknown): boolean {
  return getErrorCode(error) === 'WORKFLOW_DEFINITION_INVALID' || isValidationError(error)
}

/** Maps API import failures to user-friendly messages without exposing raw backend details. */
export function getImportWorkflowApiErrorMessage(error: unknown): string {
  const code = getErrorCode(error)

  if (code === 'WORKFLOW_NAME_CONFLICT') {
    return IMPORT_NAME_CONFLICT_MESSAGE
  }

  if (isInvalidFormatApiError(error)) {
    return IMPORT_INVALID_FORMAT_MESSAGE
  }

  return IMPORT_DEFAULT_ERROR_MESSAGE
}

/** Preserves actionable client-side parse errors for inline field display. */
export function getImportWorkflowFileErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message
  }

  return IMPORT_INVALID_FORMAT_MESSAGE
}

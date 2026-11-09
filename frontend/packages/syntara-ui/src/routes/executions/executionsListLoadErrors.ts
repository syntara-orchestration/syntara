import { isForbiddenError, isServiceUnavailableError } from '../../utils/apiErrors'

export const EXECUTIONS_LIST_LOAD_FORBIDDEN_MESSAGE = 'You do not have permission to view executions in this project.'

export const EXECUTIONS_LIST_LOAD_UNAVAILABLE_MESSAGE =
  'The workflow service is temporarily unavailable. Try again in a few minutes.'

export const EXECUTIONS_LIST_LOAD_DEFAULT_MESSAGE = 'Unable to load workflow runs. Try again.'

/** Maps executions list API failures to user-facing copy without raw backend details. */
export function getExecutionsListLoadErrorMessage(error: unknown): string {
  if (isForbiddenError(error)) {
    return EXECUTIONS_LIST_LOAD_FORBIDDEN_MESSAGE
  }

  if (isServiceUnavailableError(error)) {
    return EXECUTIONS_LIST_LOAD_UNAVAILABLE_MESSAGE
  }

  return EXECUTIONS_LIST_LOAD_DEFAULT_MESSAGE
}

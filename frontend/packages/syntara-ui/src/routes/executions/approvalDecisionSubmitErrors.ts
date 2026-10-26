import { getErrorStatus } from '../../utils/apiErrors'

export const APPROVAL_DECISION_ALREADY_RESOLVED_MESSAGE = 'This approval has already been resolved by another user.'

export const APPROVAL_DECISION_FORBIDDEN_MESSAGE = 'You do not have permission to approve or reject this request.'

export const APPROVAL_DECISION_SERVICE_UNAVAILABLE_MESSAGE =
  'The approval service is temporarily unavailable. Try again in a few minutes.'

export const APPROVAL_DECISION_DEFAULT_ERROR_MESSAGE = 'Could not submit your decision. Please try again.'

/** Maps approval decision PATCH failures to user-friendly messages without exposing raw API details. */
export function getApprovalDecisionSubmitErrorMessage(error: unknown): string {
  const status = getErrorStatus(error)

  if (status === 409) {
    return APPROVAL_DECISION_ALREADY_RESOLVED_MESSAGE
  }

  if (status === 403) {
    return APPROVAL_DECISION_FORBIDDEN_MESSAGE
  }

  if (status === 503) {
    return APPROVAL_DECISION_SERVICE_UNAVAILABLE_MESSAGE
  }

  return APPROVAL_DECISION_DEFAULT_ERROR_MESSAGE
}

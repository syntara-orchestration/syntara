import { describe, expect, it } from 'vitest'

import {
  APPROVAL_DECISION_ALREADY_RESOLVED_MESSAGE,
  APPROVAL_DECISION_DEFAULT_ERROR_MESSAGE,
  APPROVAL_DECISION_FORBIDDEN_MESSAGE,
  APPROVAL_DECISION_SERVICE_UNAVAILABLE_MESSAGE,
  getApprovalDecisionSubmitErrorMessage,
} from './approvalDecisionSubmitErrors'

describe('getApprovalDecisionSubmitErrorMessage', () => {
  it('maps 409 to already resolved message', () => {
    expect(getApprovalDecisionSubmitErrorMessage({ status: 409, detail: 'Conflict' })).toBe(
      APPROVAL_DECISION_ALREADY_RESOLVED_MESSAGE
    )
  })

  it('maps 403 to permission message', () => {
    expect(getApprovalDecisionSubmitErrorMessage({ status: 403, detail: 'Forbidden' })).toBe(
      APPROVAL_DECISION_FORBIDDEN_MESSAGE
    )
  })

  it('maps authorization error codes without http status to permission message', () => {
    expect(
      getApprovalDecisionSubmitErrorMessage({
        code: 'AUTHORIZATION_DENIED',
        detail: 'Not authorized to decide this approval',
      })
    ).toBe(APPROVAL_DECISION_FORBIDDEN_MESSAGE)
  })

  it('maps 503 to service unavailable message', () => {
    expect(getApprovalDecisionSubmitErrorMessage({ status: 503, detail: 'Unavailable' })).toBe(
      APPROVAL_DECISION_SERVICE_UNAVAILABLE_MESSAGE
    )
  })

  it('maps temporal unavailable error code to service unavailable message', () => {
    expect(getApprovalDecisionSubmitErrorMessage({ code: 'TEMPORAL_UNAVAILABLE', detail: 'Worker down' })).toBe(
      APPROVAL_DECISION_SERVICE_UNAVAILABLE_MESSAGE
    )
  })

  it('uses default message for other errors without exposing raw detail', () => {
    expect(getApprovalDecisionSubmitErrorMessage({ status: 500, detail: 'Internal server error' })).toBe(
      APPROVAL_DECISION_DEFAULT_ERROR_MESSAGE
    )
    expect(getApprovalDecisionSubmitErrorMessage({ detail: 'Something went wrong' })).toBe(
      APPROVAL_DECISION_DEFAULT_ERROR_MESSAGE
    )
  })
})

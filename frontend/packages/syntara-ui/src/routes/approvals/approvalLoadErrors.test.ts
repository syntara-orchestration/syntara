import { describe, expect, it } from 'vitest'

import { getApprovalLoadErrorAlert, getApprovalLoadErrorDescription } from './approvalLoadErrors'

describe('getApprovalLoadErrorDescription', () => {
  it('maps 404 to a not-found message', () => {
    expect(getApprovalLoadErrorDescription({ response: { status: 404 } })).toBe(
      'This approval is no longer available. It may have been resolved or deleted.'
    )
  })

  it('maps approval-not-found error codes without HTTP status', () => {
    expect(getApprovalLoadErrorDescription({ code: 'APPROVAL_NOT_FOUND' })).toBe(
      'This approval is no longer available. It may have been resolved or deleted.'
    )
    expect(getApprovalLoadErrorDescription({ code: 'RESOURCE_NOT_FOUND' })).toBe(
      'This approval is no longer available. It may have been resolved or deleted.'
    )
    expect(getApprovalLoadErrorDescription({ code: 'HTTP_404' })).toBe(
      'This approval is no longer available. It may have been resolved or deleted.'
    )
  })

  it('maps 403 to a permission message', () => {
    expect(getApprovalLoadErrorDescription({ response: { status: 403 } })).toBe(
      'You do not have permission to view this approval.'
    )
  })

  it('maps forbidden error codes without status', () => {
    expect(getApprovalLoadErrorDescription({ code: 'FORBIDDEN' })).toBe(
      'You do not have permission to view this approval.'
    )
  })

  it('uses the default message for other failures', () => {
    expect(getApprovalLoadErrorDescription(new Error('Network error'))).toBe(
      'Could not load approval details. Please try again.'
    )
    expect(getApprovalLoadErrorDescription({ response: { status: 500 } })).toBe(
      'Could not load approval details. Please try again.'
    )
  })
})

describe('getApprovalLoadErrorAlert', () => {
  it('returns title and mapped description', () => {
    expect(getApprovalLoadErrorAlert({ response: { status: 404 } })).toEqual({
      title: 'Failed to load approval',
      description: 'This approval is no longer available. It may have been resolved or deleted.',
    })
  })
})

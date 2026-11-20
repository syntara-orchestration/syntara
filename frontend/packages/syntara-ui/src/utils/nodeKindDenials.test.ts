import { describe, expect, it } from 'vitest'

import { getErrorMessage } from './apiErrors'
import { extractNodeKindDenials, getNodeKindWriteDeniedMessage, isNodeKindWriteDeniedError } from './nodeKindDenials'

const blocked = { kind: 'script', label: 'Script', reason: 'explicit_deny' }
const detail = "You can't save workflow: Script (write denied)."
const message = "This workflow includes Script steps, but your assigned policies don't allow you to write them."
const denial = { code: 'NODE_KIND_WRITE_DENIED', detail, blocked_step_types: [blocked] }

describe('step-type denial errors', () => {
  it.each([
    ['direct', denial],
    ['cause', { cause: denial }],
    ['data', { data: denial }],
    ['nested', { cause: { data: denial } }],
    ['native Error', new Error('Request failed', { cause: denial })],
  ])('formats blocked types from %s errors', (_name, error) => {
    expect(isNodeKindWriteDeniedError(error)).toBe(true)
    expect(extractNodeKindDenials(error)).toEqual([blocked])
    expect(getErrorMessage(error)).toBe(message)
  })

  it.each(['save', 'import', 'duplicate', 'restore', 'rename', 'delete', 'edit version metadata'])(
    'formats a rejected %s from structured labels without parsing the detail',
    (action) => {
      expect(getErrorMessage({ cause: { ...denial, detail: `Server explanation for ${action}.` } })).toBe(message)
    }
  )

  it.each(['explicit_deny', 'no_matching_allow'])('uses the same message for %s without policy details', (reason) => {
    const error = { ...denial, blocked_step_types: [{ ...blocked, reason, policy: 'private-policy', scope: 'any' }] }
    expect(getErrorMessage(error)).toBe(message)
  })

  it.each([
    [{ kind: 'wait', label: 'Wait', reason: 'no_matching_allow' }],
    [{ kind: 'http_request', label: 'REST API', reason: 'explicit_deny' }, blocked],
    [{ kind: 'custom_step', label: 'Custom Step', reason: 'explicit_deny' }],
  ])('uses response labels for blocked types: %j', (...blockedStepTypes) => {
    const error = { ...denial, blocked_step_types: blockedStepTypes }
    const labels = blockedStepTypes.map(({ label }) => label).join(', ')
    expect(getErrorMessage(error)).toBe(
      `This workflow includes ${labels} steps, but your assigned policies don't allow you to write them.`
    )
    expect(getNodeKindWriteDeniedMessage(error, true)).toBe(
      `This project includes workflows with ${labels} steps, but your assigned policies don't allow you to write them.`
    )
  })

  it.each([undefined, null, {}, [], [null, {}, { ...blocked, reason: 'unknown' }], [{ ...blocked, label: ' ' }]])(
    'preserves the existing detail for malformed blocked types: %j',
    (blockedStepTypes) => {
      const error = { ...denial, blocked_step_types: blockedStepTypes }
      expect(extractNodeKindDenials(error)).toEqual([])
      expect(getNodeKindWriteDeniedMessage(error)).toBeUndefined()
      expect(getErrorMessage(error)).toBe(detail)
    }
  )

  it('ignores malformed entries alongside valid blocked types', () => {
    expect(getErrorMessage({ ...denial, blocked_step_types: [null, {}, blocked] })).toBe(message)
    expect(getErrorMessage({ code: denial.code })).toBe('An unexpected error occurred')
  })

  it('handles unrelated errors and cyclic wrappers', () => {
    const error: { cause?: unknown; data?: unknown } = {}
    error.cause = error
    for (const value of [undefined, null, 42, 'error', {}, error]) {
      expect(isNodeKindWriteDeniedError(value)).toBe(false)
      expect(extractNodeKindDenials(value)).toEqual([])
      expect(getNodeKindWriteDeniedMessage(value)).toBeUndefined()
    }
    expect(getErrorMessage(error)).toBe('An unexpected error occurred')
    error.data = denial
    expect(getErrorMessage(error)).toBe(message)
    expect(getErrorMessage({ ...denial, code: 'OTHER_ERROR' })).toBe(detail)
  })

  it('sanitizes response labels before displaying them', () => {
    const error = { ...denial, blocked_step_types: [{ ...blocked, label: '<script>Denied</script> Script\u0000' }] }
    expect(getErrorMessage(error)).toBe(
      "This workflow includes Denied Script steps, but your assigned policies don't allow you to write them."
    )
  })
})

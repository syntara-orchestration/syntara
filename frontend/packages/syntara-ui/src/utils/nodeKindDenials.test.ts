import { describe, expect, it } from 'vitest'

import { getErrorMessage } from './apiErrors'
import { extractNodeKindDenials, isNodeKindWriteDeniedError } from './nodeKindDenials'

const blocked = { kind: 'script', label: 'Script', reason: 'explicit_deny' }
const denial = { code: 'NODE_KIND_WRITE_DENIED', blocked_step_types: [blocked] }

describe('step-type denial errors', () => {
  it.each([
    ['direct', denial],
    ['cause', { cause: denial }],
    ['data', { data: denial }],
    ['nested', { cause: { data: denial } }],
    ['native Error', new Error('Request failed', { cause: denial })],
  ])('extracts blocked types from %s errors', (_name, error) => {
    expect(isNodeKindWriteDeniedError(error)).toBe(true)
    expect(extractNodeKindDenials(error)).toEqual([blocked])
    expect(getErrorMessage(error)).toBe('Step types not allowed: Script (write denied).')
  })

  it.each(['save', 'import', 'duplicate', 'restore', 'rename', 'delete', 'edit version metadata', 'delete project'])(
    'preserves the rejected %s action and display label',
    (action) => {
      const detail = `You can't ${action}: Script (write denied).`
      expect(getErrorMessage({ cause: { ...denial, detail } })).toBe(detail)
    }
  )

  it('explains a missing grant without inventing a denying policy', () => {
    const error = {
      code: 'NODE_KIND_WRITE_DENIED',
      blocked_step_types: [{ ...blocked, reason: 'no_matching_allow', policy: 'private-policy', scope: 'any' }],
    }
    expect(getErrorMessage(error)).toBe('Step types not allowed: Script (no matching write grant).')
  })

  it('ignores malformed blocked types and handles missing arrays', () => {
    expect(
      extractNodeKindDenials({ ...denial, blocked_step_types: [null, {}, { ...blocked, reason: 'unknown' }] })
    ).toEqual([])
    expect(extractNodeKindDenials({ code: denial.code })).toEqual([])
    expect(getErrorMessage({ code: denial.code })).toBe('Step types not allowed.')
  })

  it('handles unrelated errors and cyclic wrappers', () => {
    const error: { cause?: unknown } = {}
    error.cause = error
    for (const value of [undefined, null, 42, 'error', {}, error]) {
      expect(isNodeKindWriteDeniedError(value)).toBe(false)
      expect(extractNodeKindDenials(value)).toEqual([])
    }
  })

  it('sanitizes denial messages before displaying them', () => {
    expect(getErrorMessage({ ...denial, detail: '<script>Denied</script> Script\u0000' })).toBe('Denied Script')
  })
})

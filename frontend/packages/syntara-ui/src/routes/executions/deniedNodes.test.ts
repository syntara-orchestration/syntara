import { describe, expect, it } from 'vitest'

import { formatNodeDeniedError, NODE_EXECUTE_DENIED_CODE, parseDeniedNodes } from './deniedNodes'

describe('parseDeniedNodes', () => {
  it('returns an empty list for null, undefined and non-arrays', () => {
    expect(parseDeniedNodes(null)).toEqual([])
    expect(parseDeniedNodes(undefined)).toEqual([])
    expect(parseDeniedNodes({ node_id: 'a' })).toEqual([])
  })

  it('narrows well-formed entries', () => {
    expect(
      parseDeniedNodes([
        {
          node_id: 'restart_service',
          kind: 'http_request',
          labels: { kind: 'http_request', method: 'post' },
          denied_by: 'no-restarts',
        },
      ])
    ).toEqual([
      {
        nodeId: 'restart_service',
        kind: 'http_request',
        labels: { kind: 'http_request', method: 'post' },
        deniedBy: 'no-restarts',
      },
    ])
  })

  it('keeps entries with only a node id', () => {
    expect(parseDeniedNodes([{ node_id: 'step_a' }])).toEqual([
      { nodeId: 'step_a', kind: undefined, labels: undefined, deniedBy: undefined },
    ])
  })

  it('drops entries without a usable node id', () => {
    expect(parseDeniedNodes([{ kind: 'script' }, { node_id: '' }, 'nope', null, [{ node_id: 'x' }]])).toEqual([])
  })
})

describe('formatNodeDeniedError', () => {
  it('returns null when there are no error details', () => {
    expect(formatNodeDeniedError(null)).toBeNull()
    expect(formatNodeDeniedError(undefined)).toBeNull()
    expect(formatNodeDeniedError('')).toBeNull()
  })

  it('returns null for unrelated errors', () => {
    expect(formatNodeDeniedError('HTTP request failed: ReadTimeout')).toBeNull()
    expect(formatNodeDeniedError('{"code": "other_error"}')).toBeNull()
  })

  it('names the denying policy when present', () => {
    const details = JSON.stringify({ code: NODE_EXECUTE_DENIED_CODE, denied_by: 'no-restarts-in-production' })

    expect(formatNodeDeniedError(details)).toBe(
      'This step was not allowed to run for this execution. Denied by policy "no-restarts-in-production".'
    )
  })

  it('falls back to a generic sentence when no policy is recorded', () => {
    const details = JSON.stringify({ code: NODE_EXECUTE_DENIED_CODE })

    expect(formatNodeDeniedError(details)).toBe('This step was not allowed to run for this execution.')
  })

  it('handles a non-JSON payload that still mentions the code', () => {
    expect(formatNodeDeniedError(`error: ${NODE_EXECUTE_DENIED_CODE}`)).toBe(
      'This step was not allowed to run for this execution.'
    )
  })
})

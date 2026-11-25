import { describe, expect, it } from 'vitest'

import { executionRefetchInterval } from './executionPolling'

describe('executionRefetchInterval', () => {
  it('returns 3000 when status is undefined', () => {
    expect(executionRefetchInterval({ state: { data: undefined } })).toBe(3000)
  })

  it('returns 3000 when status is pending', () => {
    expect(executionRefetchInterval({ state: { data: { status: 'pending' } } })).toBe(3000)
  })

  it('returns 3000 when status is running', () => {
    expect(executionRefetchInterval({ state: { data: { status: 'running' } } })).toBe(3000)
  })

  it('returns false when status is paused and the live stream is healthy', () => {
    expect(executionRefetchInterval({ state: { data: { status: 'paused' } } })).toBe(false)
  })

  it('returns 3000 when status is paused and the live stream is stale', () => {
    expect(executionRefetchInterval({ state: { data: { status: 'paused' } } }, true)).toBe(3000)
  })

  it('returns false when status is completed', () => {
    expect(executionRefetchInterval({ state: { data: { status: 'completed' } } })).toBe(false)
  })

  it('returns false when status is failed', () => {
    expect(executionRefetchInterval({ state: { data: { status: 'failed' } } })).toBe(false)
  })

  it('returns false when status is cancelled', () => {
    expect(executionRefetchInterval({ state: { data: { status: 'cancelled' } } })).toBe(false)
  })
})

import { describe, expect, it } from 'vitest'

import { getActivityTypeLabel, getUpstreamStepDisplayName } from './getUpstreamStepDisplayName'

describe('getActivityTypeLabel', () => {
  it('returns logic node labels from stepMetadata', () => {
    expect(getActivityTypeLabel('converge')).toBe('Converge')
    expect(getActivityTypeLabel('condition')).toBe('Condition')
    expect(getActivityTypeLabel('wait')).toBe('Wait')
  })

  it('returns executor labels from executorMetadata', () => {
    expect(getActivityTypeLabel('script')).toBe('Script')
    expect(getActivityTypeLabel('http_request')).toBe('REST API')
    expect(getActivityTypeLabel('agentic')).toBe('Task Agent')
  })

  it('returns Trigger for trigger API types', () => {
    expect(getActivityTypeLabel('manual_trigger')).toBe('Trigger')
    expect(getActivityTypeLabel('scheduled_trigger')).toBe('Trigger')
    expect(getActivityTypeLabel('webhook_trigger')).toBe('Trigger')
    expect(getActivityTypeLabel('eda_trigger')).toBe('Trigger')
    expect(getActivityTypeLabel('trigger')).toBe('Trigger')
    expect(getActivityTypeLabel('manual')).toBe('Trigger')
  })

  it('returns undefined for unknown types', () => {
    expect(getActivityTypeLabel('unknown_type')).toBeUndefined()
  })
})

describe('getUpstreamStepDisplayName', () => {
  it('uses trimmed custom name when present', () => {
    expect(getUpstreamStepDisplayName({ id: 'a', name: '  My Step  ', type: 'script' })).toBe('My Step')
  })

  it('falls back to type label when name is empty', () => {
    expect(getUpstreamStepDisplayName({ id: 'a', name: '', type: 'converge' })).toBe('Converge')
    expect(getUpstreamStepDisplayName({ id: 'a', name: '', type: 'script' })).toBe('Script')
  })

  it('falls back to type label when name is whitespace or missing', () => {
    expect(getUpstreamStepDisplayName({ id: 'a', name: '   ', type: 'wait' })).toBe('Wait')
    expect(getUpstreamStepDisplayName({ id: 'a', type: 'condition' })).toBe('Condition')
  })

  it('falls back to id when name and type label are unavailable', () => {
    expect(getUpstreamStepDisplayName({ id: 'node-xyz', name: '', type: 'unknown_type' })).toBe('node-xyz')
  })
})

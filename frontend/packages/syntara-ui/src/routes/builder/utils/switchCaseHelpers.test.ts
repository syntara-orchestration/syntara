import { describe, expect, it } from 'vitest'

import { SWITCH_CASE_PORT_PREFIX, buildSwitchCasePort, isSwitchCasePort, isValidSwitchPort } from './switchCaseHelpers'

describe('SWITCH_CASE_PORT_PREFIX', () => {
  it('equals "case_"', () => {
    expect(SWITCH_CASE_PORT_PREFIX).toBe('case_')
  })
})

describe('buildSwitchCasePort', () => {
  it('builds port for index 0', () => {
    expect(buildSwitchCasePort(0)).toBe('case_0')
  })

  it('builds port for large index', () => {
    expect(buildSwitchCasePort(99)).toBe('case_99')
  })
})

describe('isSwitchCasePort', () => {
  it('returns true for case_0', () => {
    expect(isSwitchCasePort('case_0')).toBe(true)
  })

  it('returns true for case_99', () => {
    expect(isSwitchCasePort('case_99')).toBe(true)
  })

  it('returns true for bare prefix case_', () => {
    expect(isSwitchCasePort('case_')).toBe(true)
  })

  it('returns false for null', () => {
    expect(isSwitchCasePort(null)).toBe(false)
  })

  it('returns false for undefined', () => {
    expect(isSwitchCasePort(undefined)).toBe(false)
  })

  it('returns false for empty string', () => {
    expect(isSwitchCasePort('')).toBe(false)
  })

  it('returns false for default', () => {
    expect(isSwitchCasePort('default')).toBe(false)
  })

  it('returns false for non-matching prefix', () => {
    expect(isSwitchCasePort('notcase_0')).toBe(false)
  })

  it('returns false for source handle', () => {
    expect(isSwitchCasePort('source')).toBe(false)
  })
})

describe('isValidSwitchPort', () => {
  it('accepts safe switch output handles', () => {
    expect(isValidSwitchPort('case_0')).toBe(true)
    expect(isValidSwitchPort('custom-default')).toBe(true)
  })

  it.each([null, '', 'contains a space', 'invalid/port', 'x'.repeat(101)])(
    'rejects an invalid switch output handle: %s',
    (port) => {
      expect(isValidSwitchPort(port)).toBe(false)
    }
  )
})

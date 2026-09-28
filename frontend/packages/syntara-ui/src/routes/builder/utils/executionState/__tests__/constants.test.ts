import { describe, expect, it } from 'vitest'

import {
  ACTIVITY_STATUS,
  ACTIVITY_TYPES,
  BRANCH_HANDLES,
  isBranchHandle,
  isTerminalState,
  TERMINAL_ACTIVITY_STATUSES,
} from '../executionHelpers'

describe('constants', () => {
  describe('BRANCH_HANDLES', () => {
    it('contains all branch handle values', () => {
      expect(BRANCH_HANDLES).toEqual(['true', 'false', 'approved', 'rejected', 'done', 'loop', 'default'])
    })
  })

  describe('isBranchHandle', () => {
    it('returns true for valid branch handles', () => {
      expect(isBranchHandle('true')).toBe(true)
      expect(isBranchHandle('false')).toBe(true)
      expect(isBranchHandle('approved')).toBe(true)
      expect(isBranchHandle('rejected')).toBe(true)
      expect(isBranchHandle('done')).toBe(true)
      expect(isBranchHandle('loop')).toBe(true)
      expect(isBranchHandle('default')).toBe(true)
      expect(isBranchHandle('case_0')).toBe(true)
      expect(isBranchHandle('case_1')).toBe(true)
    })

    it('returns false for null', () => {
      expect(isBranchHandle(null)).toBe(false)
    })

    it('returns false for undefined', () => {
      expect(isBranchHandle(undefined)).toBe(false)
    })

    it('returns false for invalid handles', () => {
      expect(isBranchHandle('source')).toBe(false)
      expect(isBranchHandle('target')).toBe(false)
      expect(isBranchHandle('invalid')).toBe(false)
      expect(isBranchHandle('')).toBe(false)
    })
  })

  describe('ACTIVITY_TYPES', () => {
    it('contains all activity type constants', () => {
      expect(ACTIVITY_TYPES.TASK).toBe('task')
      expect(ACTIVITY_TYPES.LOOP).toBe('loop')
      expect(ACTIVITY_TYPES.CONDITION).toBe('condition')
      expect(ACTIVITY_TYPES.CONVERGE).toBe('converge')
      expect(ACTIVITY_TYPES.APPROVAL).toBe('approval')
    })
  })

  describe('ACTIVITY_STATUS', () => {
    it('contains all activity status constants', () => {
      expect(ACTIVITY_STATUS.PENDING).toBe('pending')
      expect(ACTIVITY_STATUS.RUNNING).toBe('running')
      expect(ACTIVITY_STATUS.WAITING).toBe('waiting')
      expect(ACTIVITY_STATUS.COMPLETED).toBe('completed')
      expect(ACTIVITY_STATUS.FAILED).toBe('failed')
      expect(ACTIVITY_STATUS.RETRYING).toBe('retrying')
      expect(ACTIVITY_STATUS.SKIPPED).toBe('skipped')
      expect(ACTIVITY_STATUS.CANCELLED).toBe('cancelled')
    })

    it('has all expected status keys', () => {
      const expectedKeys = ['PENDING', 'RUNNING', 'WAITING', 'COMPLETED', 'FAILED', 'RETRYING', 'SKIPPED', 'CANCELLED']
      expect(Object.keys(ACTIVITY_STATUS)).toEqual(expectedKeys)
    })
  })

  describe('TERMINAL_ACTIVITY_STATUSES', () => {
    it('contains terminal statuses', () => {
      expect(TERMINAL_ACTIVITY_STATUSES).toContain('completed')
      expect(TERMINAL_ACTIVITY_STATUSES).toContain('failed')
      expect(TERMINAL_ACTIVITY_STATUSES).toContain('cancelled')
    })

    it('does not contain non-terminal statuses', () => {
      expect(TERMINAL_ACTIVITY_STATUSES).not.toContain('pending')
      expect(TERMINAL_ACTIVITY_STATUSES).not.toContain('running')
      expect(TERMINAL_ACTIVITY_STATUSES).not.toContain('retrying')
      expect(TERMINAL_ACTIVITY_STATUSES).not.toContain('skipped')
    })

    it('has exactly 3 terminal statuses', () => {
      expect(TERMINAL_ACTIVITY_STATUSES).toHaveLength(3)
    })
  })

  describe('isTerminalState', () => {
    it('returns true for terminal states', () => {
      expect(isTerminalState('completed')).toBe(true)
      expect(isTerminalState('failed')).toBe(true)
      expect(isTerminalState('cancelled')).toBe(true)
    })

    it('returns false for non-terminal states', () => {
      expect(isTerminalState('pending')).toBe(false)
      expect(isTerminalState('running')).toBe(false)
      expect(isTerminalState('retrying')).toBe(false)
      expect(isTerminalState('skipped')).toBe(false)
    })

    it('returns false for invalid states', () => {
      expect(isTerminalState('unknown')).toBe(false)
      expect(isTerminalState('')).toBe(false)
      expect(isTerminalState('COMPLETED')).toBe(false) // case sensitive
    })
  })
})

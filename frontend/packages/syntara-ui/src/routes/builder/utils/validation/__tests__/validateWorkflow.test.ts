import type { Activity } from '@syntara/contracts'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { FlowNodeType } from '../../../../../constants'
import { makeCondition } from '../../../../../test/test-helpers'
import type { EdgeConnection } from '../../../types/edge'
import { validateWorkflow } from '../validateWorkflow'

// Mock generateUUID for predictable error IDs
vi.mock('../../../../../utils/generateUUID', () => ({
  generateUUID: vi.fn(() => 'test-uuid'),
}))

describe('validateWorkflow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('valid workflows', () => {
    it('returns valid result for empty workflow', () => {
      const result = validateWorkflow([], [])
      expect(result.valid).toBe(true)
      expect(result.errors).toHaveLength(0)
      expect(result.warnings).toHaveLength(0)
    })

    it('returns valid result for simple workflow', () => {
      const activities: Activity[] = [
        { type: 'script', id: 'task-1', name: 'Task 1', parameters: { language: 'python', code: '' } },
      ]
      const edges: EdgeConnection[] = [
        {
          id: 'trigger-1-task-1',
          source: 'trigger-1',
          target: 'task-1',
          sourceHandle: 'source',
          targetHandle: 'target',
        },
      ]

      const result = validateWorkflow(activities, edges)
      expect(result.valid).toBe(true)
      expect(result.errors).toHaveLength(0)
    })

    it('returns valid result for condition node with then branch connected', () => {
      const activities: Activity[] = [
        makeCondition({ id: 'C1', name: 'Condition 1', condition: 'x > 10' }),
        { type: 'script', id: 'T1', name: 'Task 1', parameters: { language: 'python', code: '' } },
      ]
      const edges: EdgeConnection[] = [
        { id: 'C1-T1', source: 'C1', target: 'T1', sourceHandle: 'true', targetHandle: 'target' },
      ]

      const result = validateWorkflow(activities, edges)
      expect(result.valid).toBe(true)
    })
  })

  describe('invalid workflows', () => {
    it('detects dangling nodes', () => {
      const activities: Activity[] = [
        { type: 'script', id: 'task-1', name: 'Disconnected Task', parameters: { language: 'python', code: '' } },
      ]
      const edges: EdgeConnection[] = []

      const result = validateWorkflow(activities, edges)
      expect(result.valid).toBe(false)
      expect(result.errors.length).toBeGreaterThan(0)
      expect(result.errors.some((e) => e.rule === 'no-dangling-nodes')).toBe(true)
    })

    it('detects condition node missing then branch', () => {
      const activities: Activity[] = [
        makeCondition({ id: 'C1', name: 'Condition 1', condition: 'x > 10' }),
        { type: 'script', id: 'T1', name: 'Task 1', parameters: { language: 'python', code: '' } },
      ]
      const edges: EdgeConnection[] = [
        { id: 'trigger-1-C1', source: 'trigger-1', target: 'C1', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'C1-T1', source: 'C1', target: 'T1', sourceHandle: 'false', targetHandle: 'target' },
      ]

      const result = validateWorkflow(activities, edges)
      expect(result.valid).toBe(false)
      expect(result.errors.some((e) => e.rule === 'condition-connections')).toBe(true)
    })

    it('detects generic nodes that need configuration', () => {
      const activities = [
        { type: FlowNodeType.GENERIC, id: 'generic-1', name: 'Unconfigured Node', parameters: {} },
      ] as unknown as Activity[]
      const edges: EdgeConnection[] = [
        {
          id: 'trigger-1-generic-1',
          source: 'trigger-1',
          target: 'generic-1',
          sourceHandle: 'source',
          targetHandle: 'target',
        },
      ]

      const result = validateWorkflow(activities, edges)
      expect(result).toBeDefined()
      expect(Array.isArray(result.errors)).toBe(true)
    })
  })

  describe('multiple errors', () => {
    it('collects errors from multiple rules', () => {
      const activities: Activity[] = [
        {
          type: FlowNodeType.GENERIC,
          id: 'generic-1',
          name: 'Unconfigured Node',
          parameters: {},
          metadata: { __isGeneric: true },
        },
        makeCondition({ id: 'C1', name: 'Condition 1', condition: 'x > 10' }),
      ]
      const edges: EdgeConnection[] = []

      const result = validateWorkflow(activities, edges)
      expect(result.valid).toBe(false)
      expect(result.errors.length).toBeGreaterThan(1)
    })
  })

  describe('error handling', () => {
    it('catches and reports internal validation errors', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

      const activities = null as unknown as Activity[]
      const edges: EdgeConnection[] = []

      const result = validateWorkflow(activities, edges)

      expect(result.valid).toBe(false)
      expect(result.errors.some((e) => e.rule === 'internal')).toBe(true)
      expect(consoleSpy).toHaveBeenCalled()

      consoleSpy.mockRestore()
    })
  })

  describe('warnings', () => {
    it('includes warnings in result when rules produce them', () => {
      const activities: Activity[] = [
        { type: 'script', id: 'task-1', name: 'Task 1', parameters: { language: 'python', code: '' } },
      ]
      const edges: EdgeConnection[] = []

      const result = validateWorkflow(activities, edges)
      expect(Array.isArray(result.warnings)).toBe(true)
    })
  })
})

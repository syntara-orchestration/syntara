import type { Activity } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { buildNestedConditionStructure } from './buildNestedStructure'

/**
 * In v2, buildNestedConditionStructure is an identity operation.
 * These tests verify v2 flat activities pass through unchanged.
 */
describe('buildNestedConditionStructure (v2)', () => {
  describe('Simple conditions', () => {
    it('returns flat activities unchanged', () => {
      const activities: Activity[] = [
        { type: 'condition', id: 'A', name: 'Condition A', parameters: { condition: 'input.value > 10' } },
        { type: 'script_python', id: 'B', name: 'Task B', parameters: { code: 'print("B")' } },
      ]
      const edges = [{ id: 'A-B', source: 'A', target: 'B', sourceHandle: 'true', targetHandle: 'target' }]

      const result = buildNestedConditionStructure(activities, edges)

      expect(result).toHaveLength(2)
      expect(result[0].id).toBe('A')
      expect(result[1].id).toBe('B')
    })

    it('returns all activities for then and else branches', () => {
      const activities: Activity[] = [
        { type: 'condition', id: 'A', name: 'Condition A', parameters: { condition: 'input.value > 10' } },
        { type: 'script_python', id: 'B', name: 'Task B', parameters: { code: 'print("B")' } },
        { type: 'script_python', id: 'C', name: 'Task C', parameters: { code: 'print("C")' } },
      ]
      const edges = [
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'true', targetHandle: 'target' },
        { id: 'A-C', source: 'A', target: 'C', sourceHandle: 'false', targetHandle: 'target' },
      ]

      const result = buildNestedConditionStructure(activities, edges)

      expect(result).toHaveLength(3)
    })
  })

  describe('Nested conditions', () => {
    it('returns all flat activities including nested conditions', () => {
      const activities: Activity[] = [
        { type: 'condition', id: 'A', name: 'Condition A', parameters: { condition: 'input.a > 10' } },
        { type: 'condition', id: 'B', name: 'Condition B', parameters: { condition: 'input.b > 20' } },
        { type: 'script_python', id: 'C', name: 'Task C', parameters: { code: 'print("C")' } },
      ]
      const edges = [
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'true', targetHandle: 'target' },
        { id: 'B-C', source: 'B', target: 'C', sourceHandle: 'true', targetHandle: 'target' },
      ]

      const result = buildNestedConditionStructure(activities, edges)

      expect(result).toHaveLength(3)
      expect(result[0].id).toBe('A')
      expect(result[1].id).toBe('B')
      expect(result[2].id).toBe('C')
    })
  })

  describe('Multiple top-level conditions', () => {
    it('returns all independent conditions and tasks', () => {
      const activities: Activity[] = [
        { type: 'condition', id: 'A', name: 'Condition A', parameters: { condition: 'input.a > 10' } },
        { type: 'script_python', id: 'B', name: 'Task B', parameters: { code: 'print("B")' } },
        { type: 'condition', id: 'C', name: 'Condition C', parameters: { condition: 'input.c > 20' } },
        { type: 'script_python', id: 'D', name: 'Task D', parameters: { code: 'print("D")' } },
      ]
      const edges = [
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'true', targetHandle: 'target' },
        { id: 'C-D', source: 'C', target: 'D', sourceHandle: 'false', targetHandle: 'target' },
      ]

      const result = buildNestedConditionStructure(activities, edges)

      expect(result).toHaveLength(4)
    })
  })

  describe('Loop structures', () => {
    it('returns loop and body activities flat', () => {
      const activities: Activity[] = [
        { type: 'loop', id: 'loop1', name: 'Process Items', parameters: { type: 'for_each', items: '${input.items}' } },
        { type: 'script_python', id: 'task1', name: 'Process Item', parameters: { code: 'echo $item' } },
      ]
      const edges = [
        { id: 'loop1-task1', source: 'loop1', target: 'task1', sourceHandle: 'loop', targetHandle: 'target' },
        { id: 'task1-loop1', source: 'task1', target: 'loop1', sourceHandle: 'source', targetHandle: 'end' },
      ]

      const result = buildNestedConditionStructure(activities, edges)

      expect(result).toHaveLength(2)
      expect(result[0].id).toBe('loop1')
      expect(result[1].id).toBe('task1')
    })

    it('round-trips loop with incoming and outgoing edges', () => {
      const activities: Activity[] = [
        { type: 'script_python', id: 'task1', name: 'Before Loop', parameters: { code: 'echo before' } },
        { type: 'loop', id: 'loop1', name: 'Process Items', parameters: { type: 'for_each', items: '${input.items}' } },
        { type: 'script_python', id: 'task2', name: 'Inside Loop', parameters: { code: 'echo inside' } },
        { type: 'script_python', id: 'task3', name: 'After Loop', parameters: { code: 'echo after' } },
      ]

      const edges = [
        { id: 'task1-loop1', source: 'task1', target: 'loop1', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'loop1-task2', source: 'loop1', target: 'task2', sourceHandle: 'loop', targetHandle: 'target' },
        { id: 'task2-loop1', source: 'task2', target: 'loop1', sourceHandle: 'source', targetHandle: 'end' },
        { id: 'loop1-task3', source: 'loop1', target: 'task3', sourceHandle: 'done', targetHandle: 'target' },
      ]

      const reNested = buildNestedConditionStructure(activities, edges)

      expect(reNested).toHaveLength(4)
      expect(reNested[0].id).toBe('task1')
      expect(reNested[1].id).toBe('loop1')
      expect(reNested[2].id).toBe('task2')
      expect(reNested[3].id).toBe('task3')
    })
  })
})

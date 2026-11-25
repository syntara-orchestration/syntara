import type { Activity } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { validateLoopNodes } from './validateLoopNodes'

/**
 * In v2, loop nodes use parameters: { type: 'for_each', items } or parameters: { type: 'do_while', condition, max_iterations }.
 * Loop body is determined by edges (sourceHandle: 'loop'), not by a nested do[] array.
 * The validateLoopNodes function checks either nested do[] or edges for loop body presence.
 */
describe('validateLoopNodes', () => {
  it('returns no errors for workflow without loop nodes', () => {
    const activities: Activity[] = [
      { type: 'script_python', id: 'task-1', name: 'Normal Task', parameters: { code: 'print("hello")' } },
      {
        type: 'condition',
        id: 'condition-1',
        name: 'Check Status',
        parameters: { condition: '${output.status == "success"}' },
      },
    ]

    const errors = validateLoopNodes(activities)
    expect(errors).toEqual([])
  })

  // Flat format tests (with edges) - primary v2 path
  describe('flat format validation (with edges)', () => {
    it('returns no errors when loop has edges from loop handle', () => {
      const activities: Activity[] = [
        {
          type: 'loop',
          id: 'loop-1',
          name: 'Loop with Body',
          parameters: { type: 'for_each', items: '${input.items}' },
        },
      ]

      const edges = [{ id: 'e1', source: 'loop-1', target: 'task-1', sourceHandle: 'loop' }]

      const errors = validateLoopNodes(activities, edges)
      expect(errors).toEqual([])
    })

    it('returns error when loop has no edges from loop handle', () => {
      const activities: Activity[] = [
        { type: 'loop', id: 'loop-1', name: 'Empty Loop', parameters: { type: 'for_each', items: '${input.items}' } },
      ]

      const edges = [{ id: 'e1', source: 'loop-1', target: 'task-1', sourceHandle: 'done' }]

      const errors = validateLoopNodes(activities, edges)
      expect(errors).toHaveLength(1)
      expect(errors[0].nodeId).toBe('loop-1')
    })

    it('returns error when loop has no edges at all', () => {
      const activities: Activity[] = [
        {
          type: 'loop',
          id: 'loop-1',
          name: 'Disconnected Loop',
          parameters: { type: 'for_each', items: '${input.items}' },
        },
      ]

      const edges: { id: string; source: string; target: string; sourceHandle?: string }[] = []

      const errors = validateLoopNodes(activities, edges)
      expect(errors).toHaveLength(1)
      expect(errors[0].nodeId).toBe('loop-1')
    })

    it('validates multiple loops with edges correctly', () => {
      const activities: Activity[] = [
        { type: 'loop', id: 'loop-1', name: 'Loop 1', parameters: { type: 'for_each', items: '${input.items1}' } },
        { type: 'loop', id: 'loop-2', name: 'Loop 2', parameters: { type: 'for_each', items: '${input.items2}' } },
      ]

      const edges = [
        { id: 'e1', source: 'loop-1', target: 'task-1', sourceHandle: 'loop' },
        // loop-2 has no loop handle edge
      ]

      const errors = validateLoopNodes(activities, edges)
      expect(errors).toHaveLength(1)
      expect(errors[0].nodeId).toBe('loop-2')
    })
  })

  it('returns error for loop without name', () => {
    const activities: Activity[] = [
      { type: 'loop', id: 'loop-1', name: '', parameters: { type: 'for_each', items: '${input.items}' } },
    ]

    // In v2, edges must be provided for the validator to detect missing loop body
    const edges: { id: string; source: string; target: string; sourceHandle?: string }[] = []
    const errors = validateLoopNodes(activities, edges)
    expect(errors).toHaveLength(1)
    expect(errors[0].message).toBe('Loop "Untitled" must have at least one activity in its body')
  })

  it('handles empty workflow', () => {
    const errors = validateLoopNodes([])
    expect(errors).toEqual([])
  })
})

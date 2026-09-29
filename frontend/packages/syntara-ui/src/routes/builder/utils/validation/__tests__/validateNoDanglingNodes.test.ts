import type { Activity } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import type { EdgeConnection } from '../../../types/edge'
import { validateNoDanglingNodes } from '../rules/validateNoDanglingNodes'

describe('validateNoDanglingNodes', () => {
  it('returns no errors for a fully connected workflow', () => {
    const activities: Activity[] = [
      { type: 'script', id: 'A', name: 'Task A', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'B', name: 'Task B', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'C', name: 'Task C', parameters: { language: 'python', code: '' } },
    ]

    const edges: EdgeConnection[] = [
      { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
      { id: 'B-C', source: 'B', target: 'C', sourceHandle: 'source', targetHandle: 'target' },
    ]

    const result = validateNoDanglingNodes(activities, edges)
    expect(result).toEqual([])
  })

  it('detects a single dangling node', () => {
    const activities: Activity[] = [
      { type: 'script', id: 'A', name: 'Task A', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'B', name: 'Task B', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'C', name: 'Task C', parameters: { language: 'python', code: '' } },
    ]

    const edges: EdgeConnection[] = [
      { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
    ]

    const result = validateNoDanglingNodes(activities, edges)
    expect(result).toHaveLength(1)
    expect(result[0]?.severity).toBe('error')
    expect(result[0]?.rule).toBe('no-dangling-nodes')
    expect(result[0]?.nodeId).toBe('C')
    expect(result[0]?.message).toContain('Task C')
  })

  it('detects multiple dangling nodes', () => {
    const activities: Activity[] = [
      { type: 'script', id: 'A', name: 'Task A', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'B', name: 'Task B', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'C', name: 'Task C', parameters: { language: 'python', code: '' } },
    ]

    const edges: EdgeConnection[] = []

    const result = validateNoDanglingNodes(activities, edges)
    expect(result).toHaveLength(3)
  })

  it('validates all activities equally (no special parallel handling)', () => {
    const activities: Activity[] = [
      { type: 'script', id: 'A', name: 'Task A', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'B', name: 'Task B', parameters: { language: 'python', code: '' } },
    ]

    const edges: EdgeConnection[] = []

    const result = validateNoDanglingNodes(activities, edges)
    expect(result).toHaveLength(2)
    expect(result.map((r) => r.nodeId).sort((a, b) => (a ?? '').localeCompare(b ?? ''))).toEqual(['A', 'B'])
  })

  it('handles complex graph with branches', () => {
    const activities: Activity[] = [
      { type: 'script', id: 'A', name: 'Task A', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'B', name: 'Task B', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'C', name: 'Task C', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'D', name: 'Task D', parameters: { language: 'python', code: '' } },
      { type: 'converge', id: 'E', name: 'Converge E', parameters: { strategy: 'all' } },
    ]

    const edges: EdgeConnection[] = [
      { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
      { id: 'A-C', source: 'A', target: 'C', sourceHandle: 'source', targetHandle: 'target' },
      { id: 'B-E', source: 'B', target: 'E', sourceHandle: 'source', targetHandle: 'target' },
      { id: 'C-E', source: 'C', target: 'E', sourceHandle: 'source', targetHandle: 'target' },
    ]

    const result = validateNoDanglingNodes(activities, edges)
    expect(result).toHaveLength(1)
    expect(result[0].nodeId).toBe('D')
  })

  it('handles empty workflow', () => {
    const result = validateNoDanglingNodes([], [])
    expect(result).toEqual([])
  })

  it('handles single node with no edges', () => {
    const activities: Activity[] = [
      { type: 'script', id: 'A', name: 'Task A', parameters: { language: 'python', code: '' } },
    ]

    const result = validateNoDanglingNodes(activities, [])
    expect(result).toHaveLength(1)
    expect(result[0].nodeId).toBe('A')
  })
})

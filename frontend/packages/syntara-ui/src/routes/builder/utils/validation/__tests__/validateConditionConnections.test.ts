import type { Activity } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import type { EdgeConnection } from '../../../types/edge'
import { validateConditionConnections } from '../rules/validateConditionConnections'

describe('validateConditionConnections', () => {
  it('returns no errors for condition with both branches connected', () => {
    const activities: Activity[] = [
      { type: 'condition', id: 'C1', name: 'Condition 1', parameters: { condition: 'x > 10' } },
      { type: 'script', id: 'T1', name: 'Task 1', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'T2', name: 'Task 2', parameters: { language: 'python', code: '' } },
    ]

    const edges: EdgeConnection[] = [
      { id: 'C1-T1', source: 'C1', target: 'T1', sourceHandle: 'true', targetHandle: 'target' },
      { id: 'C1-T2', source: 'C1', target: 'T2', sourceHandle: 'false', targetHandle: 'target' },
    ]

    const result = validateConditionConnections(activities, edges)
    expect(result).toEqual([])
  })

  it('detects missing Then branch connection', () => {
    const activities: Activity[] = [
      { type: 'condition', id: 'C1', name: 'Condition 1', parameters: { condition: 'x > 10' } },
      { type: 'script', id: 'T1', name: 'Task 1', parameters: { language: 'python', code: '' } },
    ]

    const edges: EdgeConnection[] = [
      { id: 'C1-T1', source: 'C1', target: 'T1', sourceHandle: 'false', targetHandle: 'target' },
    ]

    const result = validateConditionConnections(activities, edges)
    expect(result).toHaveLength(1)
    expect(result[0]?.severity).toBe('error')
    expect(result[0]?.rule).toBe('condition-connections')
    expect(result[0]?.nodeId).toBe('C1')
    expect(result[0]?.message).toContain('Then')
  })

  it('allows missing Else branch connection (else is optional)', () => {
    const activities: Activity[] = [
      { type: 'condition', id: 'C1', name: 'Condition 1', parameters: { condition: 'x > 10' } },
      { type: 'script', id: 'T1', name: 'Task 1', parameters: { language: 'python', code: '' } },
    ]

    const edges: EdgeConnection[] = [
      { id: 'C1-T1', source: 'C1', target: 'T1', sourceHandle: 'true', targetHandle: 'target' },
    ]

    const result = validateConditionConnections(activities, edges)
    expect(result).toEqual([])
  })

  it('detects missing Then branch (only Then is required)', () => {
    const activities: Activity[] = [
      { type: 'condition', id: 'C1', name: 'Condition 1', parameters: { condition: 'x > 10' } },
    ]

    const edges: EdgeConnection[] = []

    const result = validateConditionConnections(activities, edges)
    expect(result).toHaveLength(1)
    expect(result[0]?.severity).toBe('error')
    expect(result[0]?.rule).toBe('condition-connections')
    expect(result[0]?.nodeId).toBe('C1')
    expect(result[0]?.message).toContain('Then')
  })

  it('handles multiple condition nodes', () => {
    const activities: Activity[] = [
      { type: 'condition', id: 'C1', name: 'Condition 1', parameters: { condition: 'x > 10' } },
      { type: 'condition', id: 'C2', name: 'Condition 2', parameters: { condition: 'y < 5' } },
      { type: 'script', id: 'T1', name: 'Task 1', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'T2', name: 'Task 2', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'T3', name: 'Task 3', parameters: { language: 'python', code: '' } },
    ]

    const edges: EdgeConnection[] = [
      { id: 'C1-T1', source: 'C1', target: 'T1', sourceHandle: 'true', targetHandle: 'target' },
      { id: 'C1-T2', source: 'C1', target: 'T2', sourceHandle: 'false', targetHandle: 'target' },
      { id: 'C2-T3', source: 'C2', target: 'T3', sourceHandle: 'true', targetHandle: 'target' },
    ]

    const result = validateConditionConnections(activities, edges)
    expect(result).toEqual([])
  })

  it('ignores non-condition nodes', () => {
    const activities: Activity[] = [
      { type: 'script', id: 'T1', name: 'Task 1', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'T2', name: 'Task 2', parameters: { language: 'python', code: '' } },
    ]

    const edges: EdgeConnection[] = [
      { id: 'T1-T2', source: 'T1', target: 'T2', sourceHandle: 'source', targetHandle: 'target' },
    ]

    const result = validateConditionConnections(activities, edges)
    expect(result).toEqual([])
  })

  it('handles empty workflow', () => {
    const result = validateConditionConnections([], [])
    expect(result).toEqual([])
  })
})

import type { Activity } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import type { EdgeConnection } from '../../../types/edge'
import { validateConvergeInputs } from '../rules/validateConvergeInputs'

describe('validateConvergeInputs', () => {
  it('returns no errors for valid converge with inputs from different conditions', () => {
    const activities: Activity[] = [
      { type: 'condition', id: 'C1', name: 'Condition 1', parameters: { condition: 'x > 10' } },
      { type: 'condition', id: 'C2', name: 'Condition 2', parameters: { condition: 'y < 5' } },
      { type: 'script', id: 'T1', name: 'Task 1', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'T2', name: 'Task 2', parameters: { language: 'python', code: '' } },
      { type: 'converge', id: 'J1', name: 'Join 1', parameters: { strategy: 'all' } },
    ]

    const edges: EdgeConnection[] = [
      { id: 'C1-T1', source: 'C1', target: 'T1', sourceHandle: 'true', targetHandle: 'target' },
      { id: 'C2-T2', source: 'C2', target: 'T2', sourceHandle: 'true', targetHandle: 'target' },
      { id: 'T1-J1', source: 'T1', target: 'J1', sourceHandle: 'source', targetHandle: 'target' },
      { id: 'T2-J1', source: 'T2', target: 'J1', sourceHandle: 'source', targetHandle: 'target' },
    ]

    const result = validateConvergeInputs(activities, edges)
    expect(result).toEqual([])
  })

  it('detects converge receiving inputs from both branches of same condition', () => {
    const activities: Activity[] = [
      { type: 'condition', id: 'C1', name: 'Condition 1', parameters: { condition: 'x > 10' } },
      { type: 'script', id: 'T1', name: 'Task 1', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'T2', name: 'Task 2', parameters: { language: 'python', code: '' } },
      { type: 'converge', id: 'J1', name: 'Join 1', parameters: { strategy: 'all' } },
    ]

    const edges: EdgeConnection[] = [
      { id: 'C1-T1', source: 'C1', target: 'T1', sourceHandle: 'true', targetHandle: 'target' },
      { id: 'C1-T2', source: 'C1', target: 'T2', sourceHandle: 'false', targetHandle: 'target' },
      { id: 'T1-J1', source: 'T1', target: 'J1', sourceHandle: 'source', targetHandle: 'target' },
      { id: 'T2-J1', source: 'T2', target: 'J1', sourceHandle: 'source', targetHandle: 'target' },
    ]

    const result = validateConvergeInputs(activities, edges)
    expect(result).toHaveLength(1)
    expect(result[0]?.severity).toBe('error')
    expect(result[0]?.rule).toBe('converge-inputs')
    expect(result[0]?.nodeIds).toContain('J1')
    expect(result[0]?.nodeIds).toContain('C1')
    expect(result[0]?.message).toContain('both')
    expect(result[0]?.message).toContain('Then')
    expect(result[0]?.message).toContain('Else')
  })

  it('handles converge with direct connections from condition (no intermediate tasks)', () => {
    const activities: Activity[] = [
      { type: 'condition', id: 'C1', name: 'Condition 1', parameters: { condition: 'x > 10' } },
      { type: 'converge', id: 'J1', name: 'Join 1', parameters: { strategy: 'all' } },
    ]

    const edges: EdgeConnection[] = [
      { id: 'C1-J1-then', source: 'C1', target: 'J1', sourceHandle: 'true', targetHandle: 'target' },
      { id: 'C1-J1-else', source: 'C1', target: 'J1', sourceHandle: 'false', targetHandle: 'target' },
    ]

    const result = validateConvergeInputs(activities, edges)
    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({ severity: 'error', rule: 'converge-inputs' })
  })

  it('handles multi-level paths (condition -> task -> task -> converge)', () => {
    const activities: Activity[] = [
      { type: 'condition', id: 'C1', name: 'Condition 1', parameters: { condition: 'x > 10' } },
      { type: 'script', id: 'T1', name: 'Task 1', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'T2', name: 'Task 2', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'T3', name: 'Task 3', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'T4', name: 'Task 4', parameters: { language: 'python', code: '' } },
      { type: 'converge', id: 'J1', name: 'Join 1', parameters: { strategy: 'all' } },
    ]

    const edges: EdgeConnection[] = [
      { id: 'C1-T1', source: 'C1', target: 'T1', sourceHandle: 'true', targetHandle: 'target' },
      { id: 'T1-T2', source: 'T1', target: 'T2', sourceHandle: 'source', targetHandle: 'target' },
      { id: 'T2-J1', source: 'T2', target: 'J1', sourceHandle: 'source', targetHandle: 'target' },
      { id: 'C1-T3', source: 'C1', target: 'T3', sourceHandle: 'false', targetHandle: 'target' },
      { id: 'T3-T4', source: 'T3', target: 'T4', sourceHandle: 'source', targetHandle: 'target' },
      { id: 'T4-J1', source: 'T4', target: 'J1', sourceHandle: 'source', targetHandle: 'target' },
    ]

    const result = validateConvergeInputs(activities, edges)
    expect(result).toHaveLength(1)
    expect(result[0]?.severity).toBe('error')
    expect(result[0]?.nodeIds).toContain('J1')
    expect(result[0]?.nodeIds).toContain('C1')
  })

  it('allows converge with only one branch from a condition', () => {
    const activities: Activity[] = [
      { type: 'condition', id: 'C1', name: 'Condition 1', parameters: { condition: 'x > 10' } },
      { type: 'script', id: 'T1', name: 'Task 1', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'T2', name: 'Task 2', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'T3', name: 'Task 3', parameters: { language: 'python', code: '' } },
      { type: 'converge', id: 'J1', name: 'Join 1', parameters: { strategy: 'all' } },
    ]

    const edges: EdgeConnection[] = [
      { id: 'C1-T1', source: 'C1', target: 'T1', sourceHandle: 'true', targetHandle: 'target' },
      { id: 'T1-J1', source: 'T1', target: 'J1', sourceHandle: 'source', targetHandle: 'target' },
      { id: 'C1-T2', source: 'C1', target: 'T2', sourceHandle: 'false', targetHandle: 'target' },
      { id: 'T2-T3', source: 'T2', target: 'T3', sourceHandle: 'source', targetHandle: 'target' },
    ]

    const result = validateConvergeInputs(activities, edges)
    expect(result).toEqual([])
  })

  it('handles empty workflow', () => {
    const result = validateConvergeInputs([], [])
    expect(result).toEqual([])
  })

  it('handles cycles in graph without infinite loop', () => {
    const activities: Activity[] = [
      { type: 'condition', id: 'C1', name: 'Condition 1', parameters: { condition: 'x > 10' } },
      { type: 'script', id: 'T1', name: 'Task 1', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'T2', name: 'Task 2', parameters: { language: 'python', code: '' } },
      { type: 'converge', id: 'J1', name: 'Join 1', parameters: { strategy: 'all' } },
    ]

    const edges: EdgeConnection[] = [
      { id: 'C1-T1', source: 'C1', target: 'T1', sourceHandle: 'true', targetHandle: 'target' },
      { id: 'T1-T2', source: 'T1', target: 'T2', sourceHandle: 'source', targetHandle: 'target' },
      { id: 'T2-T1', source: 'T2', target: 'T1', sourceHandle: 'source', targetHandle: 'target' },
      { id: 'T2-J1', source: 'T2', target: 'J1', sourceHandle: 'source', targetHandle: 'target' },
    ]

    const result = validateConvergeInputs(activities, edges)
    expect(result).toEqual([])
  })

  it('uses condition ID as name when name is missing', () => {
    const activities: Activity[] = [
      { type: 'condition', id: 'C1', parameters: { condition: 'x > 10' } },
      { type: 'converge', id: 'J1', parameters: { strategy: 'all' } },
    ]

    const edges: EdgeConnection[] = [
      { id: 'C1-J1-then', source: 'C1', target: 'J1', sourceHandle: 'true', targetHandle: 'target' },
      { id: 'C1-J1-else', source: 'C1', target: 'J1', sourceHandle: 'false', targetHandle: 'target' },
    ]

    const result = validateConvergeInputs(activities, edges)
    expect(result).toHaveLength(1)
    expect(result[0].message).toContain('C1')
  })

  it('ignores converge nodes with no condition ancestors', () => {
    const activities: Activity[] = [
      { type: 'script', id: 'T1', name: 'Task 1', parameters: { language: 'python', code: '' } },
      { type: 'script', id: 'T2', name: 'Task 2', parameters: { language: 'python', code: '' } },
      { type: 'converge', id: 'J1', name: 'Join 1', parameters: { strategy: 'all' } },
    ]

    const edges: EdgeConnection[] = [
      { id: 'T1-J1', source: 'T1', target: 'J1', sourceHandle: 'source', targetHandle: 'target' },
      { id: 'T2-J1', source: 'T2', target: 'J1', sourceHandle: 'source', targetHandle: 'target' },
    ]

    const result = validateConvergeInputs(activities, edges)
    expect(result).toEqual([])
  })
})

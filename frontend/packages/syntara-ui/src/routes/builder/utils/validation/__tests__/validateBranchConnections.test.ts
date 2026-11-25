import type { Activity } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { makeCondition } from '../../../../../test/test-helpers'
import type { EdgeConnection } from '../../../types/edge'
import { validateBranchConnections } from '../rules/validateBranchConnections'

describe('validateBranchConnections', () => {
  const defaultConfig = {
    nodeFilter: (a: Activity) => a.type === 'condition',
    requiredHandle: 'true',
    nodeTypeName: 'Condition',
    branchName: 'Then',
    errorIdPrefix: 'condition-missing-then',
    ruleName: 'condition-connections',
  }

  it('returns no errors when required branch is connected', () => {
    const activities: Activity[] = [
      makeCondition({ id: 'C1', name: 'Condition 1' }),
      { type: 'script_python', id: 'T1', name: 'Task 1', parameters: { code: '' } },
    ]
    const edges: EdgeConnection[] = [
      { id: 'C1-T1', source: 'C1', target: 'T1', sourceHandle: 'true', targetHandle: 'target' },
    ]

    const result = validateBranchConnections(activities, edges, defaultConfig)
    expect(result).toEqual([])
  })

  it('detects missing required branch connection', () => {
    const activities: Activity[] = [
      makeCondition({ id: 'C1', name: 'Condition 1' }),
      { type: 'script_python', id: 'T1', name: 'Task 1', parameters: { code: '' } },
    ]
    const edges: EdgeConnection[] = [
      { id: 'C1-T1', source: 'C1', target: 'T1', sourceHandle: 'false', targetHandle: 'target' },
    ]

    const result = validateBranchConnections(activities, edges, defaultConfig)
    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({
      id: 'condition-missing-then-C1',
      severity: 'error',
      rule: 'condition-connections',
      nodeId: 'C1',
    })
  })

  it('includes node name in error message', () => {
    const activities: Activity[] = [makeCondition({ id: 'C1', name: 'My Custom Condition' })]
    const edges: EdgeConnection[] = []

    const result = validateBranchConnections(activities, edges, defaultConfig)
    expect(result).toHaveLength(1)
    expect(result[0].message).toContain('My Custom Condition')
    expect(result[0].message).toContain('Then')
  })

  it('falls back to node id when name is not provided', () => {
    const activities: Activity[] = [{ type: 'condition', id: 'C1', parameters: { condition: 'x > 10' } }]
    const edges: EdgeConnection[] = []

    const result = validateBranchConnections(activities, edges, defaultConfig)
    expect(result).toHaveLength(1)
    expect(result[0].message).toContain('C1')
  })

  it('includes suggestion in error', () => {
    const activities: Activity[] = [makeCondition({ id: 'C1', name: 'Condition 1' })]
    const edges: EdgeConnection[] = []

    const result = validateBranchConnections(activities, edges, defaultConfig)
    expect(result).toHaveLength(1)
    expect(result[0].suggestion).toBeDefined()
    expect(result[0].suggestion).toContain('Then')
    expect(result[0].suggestion).toContain('condition')
  })

  it('handles multiple nodes with missing connections', () => {
    const activities: Activity[] = [
      makeCondition({ id: 'C1', name: 'Condition 1' }),
      makeCondition({ id: 'C2', name: 'Condition 2', condition: 'y < 5' }),
    ]
    const edges: EdgeConnection[] = []

    const result = validateBranchConnections(activities, edges, defaultConfig)
    expect(result).toHaveLength(2)
    expect(result.map((e) => e.nodeId)).toEqual(['C1', 'C2'])
  })

  it('only validates nodes matching the filter', () => {
    const activities: Activity[] = [
      makeCondition({ id: 'C1', name: 'Condition 1' }),
      { type: 'script_python', id: 'T1', name: 'Task 1', parameters: { code: '' } },
    ]
    const edges: EdgeConnection[] = []

    const result = validateBranchConnections(activities, edges, defaultConfig)
    expect(result).toHaveLength(1)
    expect(result[0].nodeId).toBe('C1')
  })

  it('works with custom configuration', () => {
    const customConfig = {
      nodeFilter: (a: Activity) => a.type === 'approval',
      requiredHandle: 'approved',
      nodeTypeName: 'Approval',
      branchName: 'Approved',
      errorIdPrefix: 'approval-missing-approved',
      ruleName: 'approval-connections',
    }

    const activities: Activity[] = [
      { type: 'approval', id: 'approval-1', name: 'Approval Task', parameters: {} },
      { type: 'script_python', id: 'regular-task', name: 'Regular Task', parameters: { code: '' } },
    ]
    const edges: EdgeConnection[] = []

    const result = validateBranchConnections(activities, edges, customConfig)
    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({
      id: 'approval-missing-approved-approval-1',
      rule: 'approval-connections',
      nodeId: 'approval-1',
    })
    expect(result[0].message).toContain('Approved')
  })

  it('handles empty activities array', () => {
    const result = validateBranchConnections([], [], defaultConfig)
    expect(result).toEqual([])
  })

  it('handles empty edges array', () => {
    const activities: Activity[] = [makeCondition({ id: 'C1', name: 'Condition 1' })]

    const result = validateBranchConnections(activities, [], defaultConfig)
    expect(result).toHaveLength(1)
  })

  it('correctly identifies edges from the node', () => {
    const activities: Activity[] = [
      makeCondition({ id: 'C1', name: 'Condition 1' }),
      { type: 'script_python', id: 'T1', name: 'Task 1', parameters: { code: '' } },
    ]
    const edges: EdgeConnection[] = [
      { id: 'T1-C1', source: 'T1', target: 'C1', sourceHandle: 'source', targetHandle: 'target' },
    ]

    const result = validateBranchConnections(activities, edges, defaultConfig)
    expect(result).toHaveLength(1)
  })
})

import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ActivityState } from '../workflows/execution/types'

import type { ActivityOrderItem } from './ExecutionActivityTable'
import {
  resolveStepName,
  sortActivityOrder,
  useActivityNameMap,
  type WorkflowDefEdge,
  type WorkflowDefShape,
} from './useActivityNameMap'

vi.mock('../../stores/workflowStoreSelectors', () => ({
  useActivities: vi.fn(() => undefined),
  useTriggers: vi.fn(() => undefined),
}))

// Re-import after mock setup so we can control return values
const { useActivities, useTriggers } = await import('../../stores/workflowStoreSelectors')

describe('resolveStepName', () => {
  it('returns undefined for null nodeId', () => {
    expect(resolveStepName(new Map(), null)).toBeUndefined()
  })

  it('returns undefined for undefined nodeId', () => {
    expect(resolveStepName(new Map())).toBeUndefined()
  })

  it('returns name from map if present', () => {
    const map = new Map([['step-1', 'Fetch Data']])
    expect(resolveStepName(map, 'step-1')).toBe('Fetch Data')
  })

  it('falls back to nodeId when not in map', () => {
    expect(resolveStepName(new Map(), 'step-1')).toBe('step-1')
  })
})

describe('useActivityNameMap', () => {
  const activityStates = new Map<string, ActivityState>([
    ['task-1', { activityId: 'task-1', status: 'completed' }],
    ['task-2', { activityId: 'task-2', status: 'pending' }],
  ])

  it('builds name map from workflow definition when store is empty', () => {
    vi.mocked(useActivities).mockReturnValue(undefined)
    vi.mocked(useTriggers).mockReturnValue(undefined)

    const wfDef: WorkflowDefShape = {
      workflow: {
        activities: [
          { id: 'task-1', name: 'Fetch Data' },
          { id: 'task-2', name: 'Process' },
        ],
      },
    }

    const { result } = renderHook(() => useActivityNameMap(wfDef, activityStates))

    expect(result.current.nameMap.get('task-1')).toBe('Fetch Data')
    expect(result.current.nameMap.get('task-2')).toBe('Process')
  })

  it('prefers store activities over workflow definition', () => {
    vi.mocked(useActivities).mockReturnValue([{ id: 'task-1', name: 'Store Name', type: 'script' }] as never)
    vi.mocked(useTriggers).mockReturnValue([])

    const wfDef: WorkflowDefShape = {
      workflow: {
        activities: [{ id: 'task-1', name: 'WF Def Name' }],
      },
    }

    const { result } = renderHook(() => useActivityNameMap(wfDef, activityStates))

    expect(result.current.nameMap.get('task-1')).toBe('Store Name')
  })

  it('includes triggers from store in name map', () => {
    vi.mocked(useActivities).mockReturnValue([])
    vi.mocked(useTriggers).mockReturnValue([
      { id: 'trigger_manual', name: 'Manual Trigger', type: 'manual_trigger' },
    ] as never)

    const { result } = renderHook(() => useActivityNameMap(null, activityStates))

    expect(result.current.nameMap.get('trigger_manual')).toBe('Manual Trigger')
  })

  it('builds activityOrder from activityStates keys', () => {
    vi.mocked(useActivities).mockReturnValue(undefined)
    vi.mocked(useTriggers).mockReturnValue(undefined)

    const wfDef: WorkflowDefShape = {
      workflow: { activities: [{ id: 'task-1', name: 'Task One' }] },
    }

    const { result } = renderHook(() => useActivityNameMap(wfDef, activityStates))

    expect(result.current.activityOrder).toEqual([
      { id: 'task-1', name: 'Task One' },
      { id: 'task-2', name: undefined },
    ])
  })

  it('handles nested activities (steps, branches, loop)', () => {
    vi.mocked(useActivities).mockReturnValue(undefined)
    vi.mocked(useTriggers).mockReturnValue(undefined)

    const wfDef: WorkflowDefShape = {
      workflow: {
        activities: [
          {
            id: 'cond-1',
            name: 'Check',
            then: [{ id: 'then-1', name: 'Then Step' }],
            else: [{ id: 'else-1', name: 'Else Step' }],
          },
          {
            id: 'loop-1',
            name: 'Loop',
            loop: { do: [{ id: 'loop-body', name: 'Loop Body' }] },
          },
          {
            id: 'par-1',
            name: 'Parallel',
            branches: [
              [{ id: 'branch-a', name: 'Branch A' }],
              { id: 'branch-b', name: 'Branch B' },
              'string-branch-ignored',
            ],
          },
        ],
      },
    }

    const states = new Map<string, ActivityState>()
    const { result } = renderHook(() => useActivityNameMap(wfDef, states))

    expect(result.current.nameMap.get('then-1')).toBe('Then Step')
    expect(result.current.nameMap.get('else-1')).toBe('Else Step')
    expect(result.current.nameMap.get('loop-body')).toBe('Loop Body')
    expect(result.current.nameMap.get('branch-a')).toBe('Branch A')
    expect(result.current.nameMap.get('branch-b')).toBe('Branch B')
  })

  it('returns empty map when workflow definition is null', () => {
    vi.mocked(useActivities).mockReturnValue(undefined)
    vi.mocked(useTriggers).mockReturnValue(undefined)

    const { result } = renderHook(() => useActivityNameMap(null, new Map()))

    expect(result.current.nameMap.size).toBe(0)
    expect(result.current.activityOrder).toEqual([])
  })

  describe('loop iteration display names', () => {
    it('labels composite key iterations as 1-based', () => {
      vi.mocked(useActivities).mockReturnValue(undefined)
      vi.mocked(useTriggers).mockReturnValue(undefined)

      const wfDef: WorkflowDefShape = {
        workflow: { activities: [{ id: 'script-1', name: 'Script', type: 'script' }] },
      }
      const states = new Map<string, ActivityState>([
        ['script-1', { activityId: 'script-1', status: 'completed', iteration: 0 }],
        ['script-1#iter-1', { activityId: 'script-1#iter-1', status: 'completed', iteration: 1 }],
        ['script-1#iter-2', { activityId: 'script-1#iter-2', status: 'running', iteration: 2 }],
      ])

      const { result } = renderHook(() => useActivityNameMap(wfDef, states))

      const names = result.current.activityOrder.map((a) => a.name)
      expect(names).toEqual(['Script (Iteration 1)', 'Script (Iteration 2)', 'Script (Iteration 3)'])
    })

    it('does not label non-iteration activities', () => {
      vi.mocked(useActivities).mockReturnValue(undefined)
      vi.mocked(useTriggers).mockReturnValue(undefined)

      const wfDef: WorkflowDefShape = {
        workflow: { activities: [{ id: 'plain', name: 'Plain Node' }] },
      }
      const states = new Map<string, ActivityState>([['plain', { activityId: 'plain', status: 'completed' }]])

      const { result } = renderHook(() => useActivityNameMap(wfDef, states))

      expect(result.current.activityOrder[0].name).toBe('Plain Node')
    })
  })

  describe('v2 workflow definition (nodes[])', () => {
    it('builds name map from top-level nodes array', () => {
      vi.mocked(useActivities).mockReturnValue(undefined)
      vi.mocked(useTriggers).mockReturnValue(undefined)

      const wfDef: WorkflowDefShape = {
        nodes: [
          { id: 'task-1', name: 'My AI Agent' },
          { id: 'task-2', name: 'Data Processor' },
        ],
      }

      const { result } = renderHook(() => useActivityNameMap(wfDef, activityStates))

      expect(result.current.nameMap.get('task-1')).toBe('My AI Agent')
      expect(result.current.nameMap.get('task-2')).toBe('Data Processor')
    })

    it('v2 nodes take precedence over v1 workflow.activities', () => {
      vi.mocked(useActivities).mockReturnValue(undefined)
      vi.mocked(useTriggers).mockReturnValue(undefined)

      const wfDef: WorkflowDefShape = {
        nodes: [
          { id: 'task-1', name: 'V2 Agent Name' },
          { id: 'task-2', name: 'V2 Processor Name' },
        ],
        workflow: {
          activities: [
            { id: 'task-1', name: 'V1 Process data' },
            { id: 'task-2', name: 'V1 Send notification' },
          ],
        },
      }

      const { result } = renderHook(() => useActivityNameMap(wfDef, activityStates))

      expect(result.current.nameMap.get('task-1')).toBe('V2 Agent Name')
      expect(result.current.nameMap.get('task-2')).toBe('V2 Processor Name')
    })

    it('falls back to v1 names when v2 node has no name', () => {
      vi.mocked(useActivities).mockReturnValue(undefined)
      vi.mocked(useTriggers).mockReturnValue(undefined)

      const wfDef: WorkflowDefShape = {
        nodes: [
          { id: 'task-1', name: 'V2 Agent Name' },
          { id: 'task-2' }, // no name
        ],
        workflow: {
          activities: [
            { id: 'task-1', name: 'V1 Process data' },
            { id: 'task-2', name: 'V1 Send notification' },
          ],
        },
      }

      const { result } = renderHook(() => useActivityNameMap(wfDef, activityStates))

      expect(result.current.nameMap.get('task-1')).toBe('V2 Agent Name')
      expect(result.current.nameMap.get('task-2')).toBe('V1 Send notification')
    })

    it('falls back to v1 workflow.activities when nodes is an empty array', () => {
      vi.mocked(useActivities).mockReturnValue(undefined)
      vi.mocked(useTriggers).mockReturnValue(undefined)

      const wfDef: WorkflowDefShape = {
        nodes: [],
        workflow: {
          activities: [
            { id: 'task-1', name: 'V1 Process data' },
            { id: 'task-2', name: 'V1 Send notification' },
          ],
        },
      }

      const { result } = renderHook(() => useActivityNameMap(wfDef, activityStates))

      expect(result.current.nameMap.get('task-1')).toBe('V1 Process data')
      expect(result.current.nameMap.get('task-2')).toBe('V1 Send notification')
    })

    it('merges disjoint v2 nodes and v1 activities per-id', () => {
      vi.mocked(useActivities).mockReturnValue(undefined)
      vi.mocked(useTriggers).mockReturnValue(undefined)

      const wfDef: WorkflowDefShape = {
        nodes: [{ id: 'task-1', name: 'V2 Only Node' }],
        workflow: {
          activities: [
            { id: 'task-2', name: 'V1 Only Activity' },
            { id: 'task-3', name: 'V1 Third Activity' },
          ],
        },
      }

      const states = new Map<string, ActivityState>([
        ['task-1', { activityId: 'task-1', status: 'completed' }],
        ['task-2', { activityId: 'task-2', status: 'pending' }],
        ['task-3', { activityId: 'task-3', status: 'running' }],
      ])
      const { result } = renderHook(() => useActivityNameMap(wfDef, states))

      expect(result.current.nameMap.get('task-1')).toBe('V2 Only Node')
      expect(result.current.nameMap.get('task-2')).toBe('V1 Only Activity')
      expect(result.current.nameMap.get('task-3')).toBe('V1 Third Activity')
    })

    it('returns raw IDs when nodes have no name field and no v1 activities', () => {
      vi.mocked(useActivities).mockReturnValue(undefined)
      vi.mocked(useTriggers).mockReturnValue(undefined)

      const wfDef: WorkflowDefShape = {
        nodes: [{ id: 'task-1' }, { id: 'task-2' }],
      }

      const { result } = renderHook(() => useActivityNameMap(wfDef, activityStates))

      // Nodes without names produce no map entries — activityOrder falls back to undefined name
      expect(result.current.nameMap.get('task-1')).toBeUndefined()
      expect(result.current.nameMap.get('task-2')).toBeUndefined()
    })
  })
})

describe('sortActivityOrder', () => {
  function makeItem(id: string, name?: string): ActivityOrderItem {
    return { id, name }
  }

  function makeState(id: string, startedAt?: string | null): [string, ActivityState] {
    return [id, { activityId: id, status: 'completed', startedAt }]
  }

  it('returns items as-is when there is 0 or 1 item', () => {
    const empty: ActivityOrderItem[] = []
    const single = [makeItem('a')]
    const states = new Map<string, ActivityState>()

    expect(sortActivityOrder(empty, undefined, states)).toEqual([])
    expect(sortActivityOrder(single, undefined, states)).toEqual([makeItem('a')])
  })

  it('sorts a linear workflow in topological order', () => {
    const items = [makeItem('C'), makeItem('A'), makeItem('B')]
    const edges: WorkflowDefEdge[] = [
      { from: 'A', to: 'B' },
      { from: 'B', to: 'C' },
    ]
    const states = new Map<string, ActivityState>()

    const result = sortActivityOrder(items, edges, states)
    expect(result.map((r) => r.id)).toEqual(['A', 'B', 'C'])
  })

  it('uses startedAt as tiebreaker for parallel branches', () => {
    // trigger → branchA and trigger → branchB (both have in-degree 1 from trigger)
    // branchA started later than branchB
    const items = [makeItem('branchA'), makeItem('branchB'), makeItem('trigger')]
    const edges: WorkflowDefEdge[] = [
      { from: 'trigger', to: 'branchA' },
      { from: 'trigger', to: 'branchB' },
    ]
    const states = new Map([
      makeState('trigger', '2024-01-01T00:00:00Z'),
      makeState('branchA', '2024-01-01T00:00:05Z'),
      makeState('branchB', '2024-01-01T00:00:02Z'),
    ])

    const result = sortActivityOrder(items, edges, states)
    expect(result.map((r) => r.id)).toEqual(['trigger', 'branchB', 'branchA'])
  })

  it('falls back to startedAt sort when no edges are provided', () => {
    const items = [makeItem('c'), makeItem('a'), makeItem('b')]
    const states = new Map([
      makeState('a', '2024-01-01T00:00:01Z'),
      makeState('b', '2024-01-01T00:00:02Z'),
      makeState('c', '2024-01-01T00:00:03Z'),
    ])

    const result = sortActivityOrder(items, undefined, states)
    expect(result.map((r) => r.id)).toEqual(['a', 'b', 'c'])
  })

  it('falls back to startedAt sort when edges array is empty', () => {
    const items = [makeItem('c'), makeItem('a'), makeItem('b')]
    const states = new Map([
      makeState('a', '2024-01-01T00:00:01Z'),
      makeState('b', '2024-01-01T00:00:02Z'),
      makeState('c', '2024-01-01T00:00:03Z'),
    ])

    const result = sortActivityOrder(items, [], states)
    expect(result.map((r) => r.id)).toEqual(['a', 'b', 'c'])
  })

  it('places activities without startedAt after those with timestamps', () => {
    const items = [makeItem('no-time'), makeItem('has-time')]
    const states = new Map([makeState('has-time', '2024-01-01T00:00:01Z'), makeState('no-time', null)])

    const result = sortActivityOrder(items, undefined, states)
    expect(result.map((r) => r.id)).toEqual(['has-time', 'no-time'])
  })

  it('groups loop iterations after their base activity', () => {
    const items = [
      makeItem('step-2'),
      makeItem('loop-1#iter-1', 'Loop (Iteration 2)'),
      makeItem('step-1'),
      makeItem('loop-1', 'Loop (Iteration 1)'),
      makeItem('loop-1#iter-2', 'Loop (Iteration 3)'),
    ]
    const edges: WorkflowDefEdge[] = [
      { from: 'step-1', to: 'loop-1' },
      { from: 'loop-1', to: 'step-2' },
    ]
    const states = new Map<string, ActivityState>()

    const result = sortActivityOrder(items, edges, states)
    expect(result.map((r) => r.id)).toEqual(['step-1', 'loop-1', 'loop-1#iter-1', 'loop-1#iter-2', 'step-2'])
  })

  it('appends activities not in the graph at the end', () => {
    const items = [makeItem('orphan'), makeItem('B'), makeItem('A')]
    const edges: WorkflowDefEdge[] = [{ from: 'A', to: 'B' }]
    const states = new Map<string, ActivityState>()

    const result = sortActivityOrder(items, edges, states)
    expect(result.map((r) => r.id)).toEqual(['A', 'B', 'orphan'])
  })

  it('skips loop-back edges (to_port === iterate)', () => {
    // loop-1 → body (iterate port), body → loop-1 (loop-back with to_port=iterate)
    const items = [makeItem('body'), makeItem('loop-1')]
    const edges: WorkflowDefEdge[] = [
      { from: 'loop-1', to: 'body', from_port: 'iterate' },
      { from: 'body', to: 'loop-1', to_port: 'iterate' },
    ]
    const states = new Map<string, ActivityState>()

    const result = sortActivityOrder(items, edges, states)
    // loop-1 should come before body (the iterate edge creates loop-1 → body dependency)
    expect(result.map((r) => r.id)).toEqual(['loop-1', 'body'])
  })

  it('handles condition branches (from_port true/false)', () => {
    const items = [makeItem('else-step'), makeItem('then-step'), makeItem('condition')]
    const edges: WorkflowDefEdge[] = [
      { from: 'condition', to: 'then-step', from_port: 'true' },
      { from: 'condition', to: 'else-step', from_port: 'false' },
    ]
    const states = new Map([
      makeState('condition', '2024-01-01T00:00:00Z'),
      makeState('then-step', '2024-01-01T00:00:01Z'),
      makeState('else-step', null),
    ])

    const result = sortActivityOrder(items, edges, states)
    expect(result.map((r) => r.id)).toEqual(['condition', 'then-step', 'else-step'])
  })

  it('ignores self-referencing edges', () => {
    const items = [makeItem('B'), makeItem('A')]
    const edges: WorkflowDefEdge[] = [
      { from: 'A', to: 'B' },
      { from: 'A', to: 'A' },
    ]
    const states = new Map<string, ActivityState>()

    const result = sortActivityOrder(items, edges, states)
    expect(result.map((r) => r.id)).toEqual(['A', 'B'])
  })

  it('handles orphan iteration items whose base node is not present', () => {
    const items = [makeItem('other'), makeItem('missing#iter-0'), makeItem('missing#iter-1')]
    const states = new Map<string, ActivityState>()

    const result = sortActivityOrder(items, undefined, states)
    // 'other' is a base item, iterations of 'missing' are appended at the end
    expect(result.map((r) => r.id)).toEqual(['other', 'missing#iter-0', 'missing#iter-1'])
  })
})

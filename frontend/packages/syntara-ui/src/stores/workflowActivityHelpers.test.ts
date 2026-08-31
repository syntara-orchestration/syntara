import { ActivityTypeEnum, EdgeHandleEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import {
  collectAllActivityIds,
  findActivityById,
  getValidSourceHandles,
  remapSwitchEdges,
  removeActivityFromList,
  updateActivityInList,
  reorderActivities,
} from './workflowActivityHelpers'
import type { Activity } from './workflowStoreTypes'

// v2: all nodes are flat with a config object, no nested structures
const task = (id: string): Activity => ({ type: ActivityTypeEnum.SCRIPT, id, name: id, parameters: {} })

const condition = (id: string): Activity => ({
  type: ActivityTypeEnum.CONDITION,
  id,
  name: id,
  parameters: { condition: 'true' },
})

const loop = (id: string): Activity => ({
  type: ActivityTypeEnum.LOOP,
  id,
  name: id,
  parameters: { type: 'for_each', items: 'items' },
})

const converge = (id: string): Activity => ({
  type: ActivityTypeEnum.CONVERGE,
  id,
  name: id,
  parameters: { strategy: 'all' },
})

describe('findActivityById', () => {
  it('finds top-level activity', () => {
    const result = findActivityById([task('a'), task('b')], 'b')
    expect(result?.id).toBe('b')
  })

  it('returns null when not found', () => {
    expect(findActivityById([task('a')], 'z')).toBeNull()
  })

  it('finds condition node in flat list', () => {
    const activities = [condition('c1'), task('a')]
    expect(findActivityById(activities, 'c1')?.id).toBe('c1')
  })

  it('finds loop node in flat list', () => {
    const activities = [loop('l1'), task('a')]
    expect(findActivityById(activities, 'l1')?.id).toBe('l1')
  })

  it('finds converge node in flat list', () => {
    const activities = [converge('j1'), task('a')]
    expect(findActivityById(activities, 'j1')?.id).toBe('j1')
  })
})

describe('removeActivityFromList', () => {
  it('removes top-level activity', () => {
    const result = removeActivityFromList([task('a'), task('b')], 'a')
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('b')
  })

  it('removes condition node from flat list', () => {
    const activities = [condition('c1'), task('a')]
    const result = removeActivityFromList(activities, 'c1')
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('a')
  })

  it('removes loop node from flat list', () => {
    const activities = [loop('l1'), task('a')]
    const result = removeActivityFromList(activities, 'l1')
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('a')
  })

  it('removes converge node from flat list', () => {
    const activities = [converge('j1'), task('a'), task('b')]
    const result = removeActivityFromList(activities, 'j1')
    expect(result).toHaveLength(2)
    expect(result[0].id).toBe('a')
    expect(result[1].id).toBe('b')
  })

  it('returns empty array when removing only element', () => {
    const activities = [task('a')]
    const result = removeActivityFromList(activities, 'a')
    expect(result).toHaveLength(0)
  })

  it('returns unchanged list when id not found', () => {
    const activities = [task('a'), task('b')]
    const result = removeActivityFromList(activities, 'z')
    expect(result).toHaveLength(2)
  })
})

describe('updateActivityInList', () => {
  it('updates top-level activity', () => {
    const result = updateActivityInList([task('a')], 'a', { name: 'updated' })
    expect(result[0].name).toBe('updated')
  })

  it('updates condition node in flat list', () => {
    const activities = [condition('c1'), task('a')]
    const result = updateActivityInList(activities, 'c1', { name: 'updated' })
    expect(result[0].name).toBe('updated')
    expect(result[0].type).toBe(ActivityTypeEnum.CONDITION)
  })

  it('updates loop node in flat list', () => {
    const activities = [loop('l1'), task('a')]
    const result = updateActivityInList(activities, 'l1', { name: 'updated' })
    expect(result[0].name).toBe('updated')
    expect(result[0].type).toBe(ActivityTypeEnum.LOOP)
  })

  it('returns unchanged activity when id not found', () => {
    const activities = [task('a')]
    const result = updateActivityInList(activities, 'z', { name: 'nope' })
    expect(result[0].name).toBe('a')
  })
})

describe('reorderActivities', () => {
  it('reorders based on edge connections', () => {
    const activities = [task('b'), task('a')]
    const edges = [{ id: 'e1', source: 'a', target: 'b', sourceHandle: 'source', targetHandle: 'target' }]
    const result = reorderActivities(activities, edges)
    expect(result[0].id).toBe('a')
    expect(result[1].id).toBe('b')
  })

  it('orders condition node based on edges', () => {
    const activities = [task('after'), condition('c1')]
    const edges = [{ id: 'e1', source: 'c1', target: 'after', sourceHandle: 'source', targetHandle: 'target' }]
    const result = reorderActivities(activities, edges)
    expect(result[0].id).toBe('c1')
    expect(result[1].id).toBe('after')
  })

  it('orders loop node based on edges', () => {
    const activities = [task('after'), loop('l1')]
    const edges = [{ id: 'e1', source: 'l1', target: 'after', sourceHandle: 'source', targetHandle: 'target' }]
    const result = reorderActivities(activities, edges)
    expect(result[0].id).toBe('l1')
    expect(result[1].id).toBe('after')
  })

  it('skips branch edges (loop, true, false)', () => {
    const activities = [task('a'), task('b')]
    const edges = [{ id: 'e1', source: 'a', target: 'b', sourceHandle: 'loop', targetHandle: 'target' }]
    const result = reorderActivities(activities, edges)
    expect(result.map((a) => a.id)).toEqual(['a', 'b'])
  })

  it('skips loop-back edges', () => {
    const activities = [task('a'), task('b')]
    const edges = [{ id: 'e1', source: 'b', target: 'a', sourceHandle: 'source', targetHandle: 'end' }]
    const result = reorderActivities(activities, edges)
    expect(result.map((a) => a.id)).toEqual(['a', 'b'])
  })

  it('preserves activities with no connections', () => {
    const activities = [task('a'), task('b'), task('c')]
    const edges = [{ id: 'e1', source: 'a', target: 'b', sourceHandle: 'source', targetHandle: 'target' }]
    const result = reorderActivities(activities, edges)
    expect(result).toHaveLength(3)
    expect(result.some((a) => a.id === 'c')).toBe(true)
  })

  it('uses safety check to include activities lost during topological sort cycle', () => {
    const activities = [task('a'), task('b'), task('c')]
    const edges = [
      { id: 'e1', source: 'a', target: 'b', sourceHandle: 'source', targetHandle: 'target' },
      { id: 'e2', source: 'b', target: 'a', sourceHandle: 'source', targetHandle: 'target' },
    ]
    const result = reorderActivities(activities, edges)
    expect(result).toHaveLength(3)
    expect(result.some((a) => a.id === 'a')).toBe(true)
    expect(result.some((a) => a.id === 'b')).toBe(true)
    expect(result.some((a) => a.id === 'c')).toBe(true)
  })

  it('handles self-referencing edge gracefully', () => {
    const activities = [task('a'), task('b')]
    const edges = [
      { id: 'e1', source: 'a', target: 'a', sourceHandle: 'source', targetHandle: 'target' },
      { id: 'e2', source: 'a', target: 'b', sourceHandle: 'source', targetHandle: 'target' },
    ]
    const result = reorderActivities(activities, edges)
    expect(result).toHaveLength(2)
    expect(result[0].id).toBe('a')
    expect(result[1].id).toBe('b')
  })
})

describe('collectAllActivityIds', () => {
  it('collects top-level activity IDs', () => {
    const ids = collectAllActivityIds([task('a'), task('b')])
    expect(ids).toEqual(new Set(['a', 'b']))
  })

  it('collects IDs from flat list with mixed types', () => {
    const ids = collectAllActivityIds([condition('c1'), task('a'), loop('l1')])
    expect(ids).toEqual(new Set(['c1', 'a', 'l1']))
  })

  it('collects IDs from flat list with converge', () => {
    const ids = collectAllActivityIds([converge('j1'), task('a')])
    expect(ids).toEqual(new Set(['j1', 'a']))
  })

  it('collects all IDs from complex flat list', () => {
    const ids = collectAllActivityIds([condition('c1'), task('a'), loop('l1'), converge('j1'), task('b')])
    expect(ids).toEqual(new Set(['c1', 'a', 'l1', 'j1', 'b']))
  })
})

describe('getValidSourceHandles', () => {
  it('returns DEFAULT for switch activity type', () => {
    const handles = getValidSourceHandles(ActivityTypeEnum.SWITCH)
    expect(handles).toEqual(new Set([EdgeHandleEnum.DEFAULT]))
  })

  it('returns SOURCE for script activity type', () => {
    const handles = getValidSourceHandles(ActivityTypeEnum.SCRIPT)
    expect(handles).toEqual(new Set([EdgeHandleEnum.SOURCE]))
  })
})

describe('remapSwitchEdges', () => {
  const portMapping = new Map([
    ['case_0', 'case_0'],
    ['case_2', 'case_1'],
  ])

  const edge = (id: string, source: string, target: string, sourceHandle?: string) => ({
    id,
    source,
    target,
    sourceHandle,
  })

  it('remaps switch case edges according to port mapping', () => {
    const edges = [edge('e0', 'switch-1', 'node-a', 'case_0'), edge('e2', 'switch-1', 'node-c', 'case_2')]
    const result = remapSwitchEdges(edges, 'switch-1', portMapping)

    expect(result[0].sourceHandle).toBe('case_0')
    expect(result[1].sourceHandle).toBe('case_1')
  })

  it('removes edges whose port is not in the mapping', () => {
    const edges = [edge('e1', 'switch-1', 'node-b', 'case_1')]
    const result = remapSwitchEdges(edges, 'switch-1', portMapping)

    expect(result).toHaveLength(0)
  })

  it('preserves edges without sourceHandle', () => {
    const edges = [edge('e-no-handle', 'switch-1', 'node-x')]
    const result = remapSwitchEdges(edges, 'switch-1', portMapping)

    expect(result).toHaveLength(1)
    expect(result[0].target).toBe('node-x')
  })

  it('preserves default handle edges', () => {
    const edges = [edge('e-default', 'switch-1', 'node-d', EdgeHandleEnum.DEFAULT)]
    const result = remapSwitchEdges(edges, 'switch-1', portMapping)

    expect(result).toHaveLength(1)
    expect(result[0].sourceHandle).toBe(EdgeHandleEnum.DEFAULT)
  })

  it('preserves non-switch sourceHandle edges', () => {
    const edges = [edge('e-source', 'switch-1', 'node-y', EdgeHandleEnum.SOURCE)]
    const result = remapSwitchEdges(edges, 'switch-1', portMapping)

    expect(result).toHaveLength(1)
    expect(result[0].sourceHandle).toBe(EdgeHandleEnum.SOURCE)
  })

  it('does not affect edges from other nodes', () => {
    const edges = [edge('e-other', 'other-node', 'node-z', 'case_0')]
    const result = remapSwitchEdges(edges, 'switch-1', portMapping)

    expect(result).toHaveLength(1)
    expect(result[0].source).toBe('other-node')
    expect(result[0].sourceHandle).toBe('case_0')
  })
})

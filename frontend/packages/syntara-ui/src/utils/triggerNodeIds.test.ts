import { describe, expect, it } from 'vitest'

import { StepMenuCategory } from '../constants'

import { buildTriggerNodeId, parseTriggerIndex, resolveFlowNodeId, toReactFlowNodeId } from './triggerNodeIds'
describe('triggerNodeIds', () => {
  it('builds trigger node ids', () => {
    expect(buildTriggerNodeId(2)).toBe('trigger-2')
  })

  it('parses trigger index from node id', () => {
    expect(parseTriggerIndex('trigger-5')).toBe(5)
    expect(parseTriggerIndex('task-1')).toBeUndefined()
  })

  it('returns undefined for invalid trigger ids', () => {
    expect(parseTriggerIndex('trigger-')).toBeUndefined()
    expect(parseTriggerIndex('trigger-abc')).toBeUndefined()
  })

  it('parses zero index', () => {
    expect(parseTriggerIndex('trigger-0')).toBe(0)
  })

  it('resolves flow node id for trigger and activity', () => {
    expect(resolveFlowNodeId({ nodeId: 'task-1', stepCategory: StepMenuCategory.ACTIVITY })).toBe('task-1')
    expect(resolveFlowNodeId({ nodeId: 'any', stepCategory: StepMenuCategory.TRIGGER, triggerIndex: 3 })).toBe(
      'trigger-3'
    )
  })

  it('maps real trigger ids to React Flow display ids', () => {
    const triggers = [{ id: 'real-trigger-id' }, { id: 'other-trigger' }]

    expect(toReactFlowNodeId('real-trigger-id', triggers)).toBe('trigger-0')
    expect(toReactFlowNodeId('other-trigger', triggers)).toBe('trigger-1')
    expect(toReactFlowNodeId('trigger-0', triggers)).toBe('trigger-0')
    expect(toReactFlowNodeId('node-1', triggers)).toBe('node-1')
  })
})

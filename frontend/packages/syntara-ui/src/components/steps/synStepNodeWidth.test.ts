import { ExecutorTypeEnum } from '@syntara/contracts'
import type { NodeProps } from '@xyflow/react'
import { describe, expect, it } from 'vitest'

import { FlowNodeType } from '../../constants'

import { getSynStepNodeWidth, SYN_STEP_DEFAULT_NODE_WIDTH } from './synStepNodeWidth'

function nodeProps(overrides: Partial<NodeProps> & Pick<NodeProps, 'type' | 'data'>): NodeProps {
  return {
    id: 'n1',
    selected: false,
    dragging: false,
    zIndex: 0,
    isConnectable: true,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    ...overrides,
  } as NodeProps
}

describe('getSynStepNodeWidth', () => {
  it('uses default width at normal zoom for structural nodes', () => {
    const props = nodeProps({ type: 'condition', data: { id: 'a1', type: 'condition', name: 'C' } })
    expect(getSynStepNodeWidth(false, props)).toBe(SYN_STEP_DEFAULT_NODE_WIDTH)
  })

  it('uses default width at semantic zoom for all node types', () => {
    const props = nodeProps({ type: 'condition', data: { id: 'a1', type: 'condition', name: 'C' } })
    expect(getSynStepNodeWidth(true, props)).toBe(SYN_STEP_DEFAULT_NODE_WIDTH)
  })

  it('uses default width for agentic tasks at normal zoom', () => {
    const props = nodeProps({
      type: FlowNodeType.TASK,
      data: {
        id: 't1',
        type: ExecutorTypeEnum.AGENTIC,
        name: 'Agent',
        parameters: { agent: 'a', prompt: 'p' },
      },
    })
    expect(getSynStepNodeWidth(false, props)).toBe(SYN_STEP_DEFAULT_NODE_WIDTH)
  })

  it('uses default width for generic placeholder nodes', () => {
    const props = nodeProps({ type: FlowNodeType.GENERIC, data: { id: 'g1', type: 'generic', name: 'G' } })
    expect(getSynStepNodeWidth(false, props)).toBe(SYN_STEP_DEFAULT_NODE_WIDTH)
  })
})

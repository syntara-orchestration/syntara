import { ExecutorTypeEnum } from '@syntara/contracts'
import type { NodeProps } from '@xyflow/react'
import { describe, expect, it } from 'vitest'

import { FlowNodeType } from '../../constants'
import { SEMANTIC_ZOOM_TILE_SIZE_PX } from '../../routes/workflows/canvas/semanticZoom'

import { getSynStepNodeWidth, SYN_STEP_DEFAULT_NODE_WIDTH, SYN_STEP_WIDE_NODE_WIDTH } from './synStepNodeWidth'

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
  it('uses semantic zoom tile size when zoomed out', () => {
    const props = nodeProps({ type: 'condition', data: { id: 'a1', type: 'condition', name: 'C' } })
    expect(getSynStepNodeWidth(true, props)).toBe(SEMANTIC_ZOOM_TILE_SIZE_PX)
  })

  it('uses default width for structural nodes at normal zoom', () => {
    const props = nodeProps({ type: 'condition', data: { id: 'a1', type: 'condition', name: 'C' } })
    expect(getSynStepNodeWidth(false, props)).toBe(SYN_STEP_DEFAULT_NODE_WIDTH)
  })

  it('uses wide width for generic placeholder nodes', () => {
    const props = nodeProps({ type: FlowNodeType.GENERIC, data: { id: 'g1', type: 'generic', name: 'G' } })
    expect(getSynStepNodeWidth(false, props)).toBe(SYN_STEP_WIDE_NODE_WIDTH)
  })

  it('uses wide width for agentic tasks', () => {
    const props = nodeProps({
      type: FlowNodeType.TASK,
      data: {
        id: 't1',
        type: ExecutorTypeEnum.AGENTIC,
        name: 'Agent',
        parameters: { agent: 'a', prompt: 'p' },
      },
    })
    expect(getSynStepNodeWidth(false, props)).toBe(SYN_STEP_WIDE_NODE_WIDTH)
  })

  it('uses default width for non-agentic tasks', () => {
    const props = nodeProps({
      type: FlowNodeType.TASK,
      data: {
        id: 't1',
        type: ExecutorTypeEnum.SCRIPT,
        name: 'Script',
        parameters: { language: 'python', code: 'x' },
      },
    })
    expect(getSynStepNodeWidth(false, props)).toBe(SYN_STEP_DEFAULT_NODE_WIDTH)
  })

  it('uses default width for task-reversed non-agentic tasks', () => {
    const props = nodeProps({
      type: FlowNodeType.TASK_REVERSED,
      data: {
        id: 't1',
        type: ExecutorTypeEnum.SCRIPT,
        name: 'Script',
        parameters: { language: 'python', code: 'x' },
      },
    })
    expect(getSynStepNodeWidth(false, props)).toBe(SYN_STEP_DEFAULT_NODE_WIDTH)
  })

  it('uses default width when task-shaped node has no data', () => {
    const props = nodeProps({
      type: FlowNodeType.TASK,
      data: undefined as never,
    })
    expect(getSynStepNodeWidth(false, props)).toBe(SYN_STEP_DEFAULT_NODE_WIDTH)
  })
})

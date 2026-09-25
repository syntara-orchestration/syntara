import { ExecutorTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { FlowNodeType, RegistryNodeId } from '../../../constants'

import { DetectedExecutorType } from './nodes/common/detectTaskNodeType'
import { getAddNodePanelColor, getNodeTypeColor, NODE_TYPE_COLORS } from './nodeTypeColors'

describe('getNodeTypeColor', () => {
  it('returns trigger color for trigger node type', () => {
    expect(getNodeTypeColor(FlowNodeType.TRIGGER)).toBe(NODE_TYPE_COLORS.trigger)
  })

  it('returns approval color for approval node type', () => {
    expect(getNodeTypeColor(FlowNodeType.APPROVAL)).toBe(NODE_TYPE_COLORS.approval)
  })

  it('returns logic color for condition, loop, converge', () => {
    expect(getNodeTypeColor(FlowNodeType.CONDITION)).toBe(NODE_TYPE_COLORS.logic)
    expect(getNodeTypeColor(FlowNodeType.LOOP)).toBe(NODE_TYPE_COLORS.logic)
    expect(getNodeTypeColor(FlowNodeType.CONVERGE)).toBe(NODE_TYPE_COLORS.logic)
  })

  it('returns generic color for generic node type', () => {
    expect(getNodeTypeColor(FlowNodeType.GENERIC)).toBe(NODE_TYPE_COLORS.generic)
  })

  it('returns actionScript color for task with script type', () => {
    expect(
      getNodeTypeColor(FlowNodeType.TASK, {
        type: ExecutorTypeEnum.SCRIPT,
        id: 'test',
        parameters: {},
      } as Parameters<typeof getNodeTypeColor>[1])
    ).toBe(NODE_TYPE_COLORS.actionScript)
  })

  it('returns actionAap color for task with aap_job_template type', () => {
    expect(
      getNodeTypeColor(FlowNodeType.TASK, {
        type: ExecutorTypeEnum.AAP_JOB_TEMPLATE,
        id: 'test',
        parameters: {},
      } as Parameters<typeof getNodeTypeColor>[1])
    ).toBe(NODE_TYPE_COLORS.actionAap)
  })

  it('SECURITY: rejects internal-only aap type from metadata override, falls back to agentic color', () => {
    // 'aap' is internal-only — metadata.__executorType: 'aap' from untrusted workflow JSON
    // must be rejected to prevent forcing arbitrary nodes to render with AAP styling
    expect(
      getNodeTypeColor(FlowNodeType.TASK, {
        type: ExecutorTypeEnum.AGENTIC,
        id: 'test',
        parameters: {},
        metadata: { __executorType: DetectedExecutorType.AAP },
      } as Parameters<typeof getNodeTypeColor>[1])
    ).toBe(NODE_TYPE_COLORS.actionAgentic)
  })

  it('returns actionAgentic color for task with agentic type', () => {
    expect(
      getNodeTypeColor(FlowNodeType.TASK, {
        type: ExecutorTypeEnum.AGENTIC,
        id: 'test',
        parameters: {},
      } as Parameters<typeof getNodeTypeColor>[1])
    ).toBe(NODE_TYPE_COLORS.actionAgentic)
  })

  it('returns actionHttpRequest for task with http_request type', () => {
    expect(
      getNodeTypeColor(FlowNodeType.TASK, {
        type: ExecutorTypeEnum.HTTP_REQUEST,
        id: 'test',
        parameters: {},
      } as Parameters<typeof getNodeTypeColor>[1])
    ).toBe(NODE_TYPE_COLORS.actionHttpRequest)
  })

  it('returns actionDefault for task-reversed with no data', () => {
    expect(getNodeTypeColor(FlowNodeType.TASK_REVERSED)).toBe(NODE_TYPE_COLORS.actionDefault)
  })

  it('returns actionDefault for unknown node type', () => {
    expect(getNodeTypeColor('unknown')).toBe(NODE_TYPE_COLORS.actionDefault)
  })
})

describe('getAddNodePanelColor', () => {
  it('returns undefined for trigger and trigger subtypes', () => {
    expect(getAddNodePanelColor(RegistryNodeId.TRIGGER)).toBeUndefined()
    expect(getAddNodePanelColor(RegistryNodeId.TRIGGER_MANUAL)).toBeUndefined()
    expect(getAddNodePanelColor(RegistryNodeId.TRIGGER_SCHEDULED)).toBeUndefined()
  })

  it('returns logic color for logic and logic subtypes', () => {
    expect(getAddNodePanelColor(RegistryNodeId.LOGIC)).toBe(NODE_TYPE_COLORS.logic)
    expect(getAddNodePanelColor(RegistryNodeId.LOGIC_CONDITION)).toBe(NODE_TYPE_COLORS.logic)
    expect(getAddNodePanelColor(RegistryNodeId.LOGIC_CONVERGE)).toBe(NODE_TYPE_COLORS.logic)
    expect(getAddNodePanelColor(RegistryNodeId.LOGIC_LOOP)).toBe(NODE_TYPE_COLORS.logic)
  })

  it('returns approval color for approval and human tasks category', () => {
    expect(getAddNodePanelColor(RegistryNodeId.APPROVAL)).toBe(NODE_TYPE_COLORS.approval)
    expect(getAddNodePanelColor(RegistryNodeId.HUMAN_TASKS)).toBe(NODE_TYPE_COLORS.approval)
  })

  it('returns actionScript color for action and action subtypes', () => {
    expect(getAddNodePanelColor(RegistryNodeId.ACTION)).toBe(NODE_TYPE_COLORS.actionScript)
    expect(getAddNodePanelColor(RegistryNodeId.ACTION_SCRIPT)).toBe(NODE_TYPE_COLORS.actionScript)
    expect(getAddNodePanelColor(RegistryNodeId.ACTION_API)).toBe(NODE_TYPE_COLORS.actionScript)
  })

  it('returns actionAgentic color for agent', () => {
    expect(getAddNodePanelColor(RegistryNodeId.AGENT)).toBe(NODE_TYPE_COLORS.actionAgentic)
  })

  it('returns actionAap color for AAP execution category', () => {
    expect(getAddNodePanelColor(RegistryNodeId.AAP_EXECUTION)).toBe(NODE_TYPE_COLORS.actionAap)
  })

  it('returns undefined for empty or unknown registry id', () => {
    expect(getAddNodePanelColor('')).toBeUndefined()
    expect(getAddNodePanelColor('unknown')).toBeUndefined()
  })
})

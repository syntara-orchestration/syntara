import { ExecutorTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { FlowNodeType, RegistryStepId } from '../../../constants'

import { DetectedExecutorType } from './nodes/common/detectTaskExecutorType'
import { getAddStepPanelColor, getStepTypeColor, STEP_TYPE_COLORS } from './stepTypeColors'

describe('getStepTypeColor', () => {
  it('returns trigger color for trigger step type', () => {
    expect(getStepTypeColor(FlowNodeType.TRIGGER)).toBe(STEP_TYPE_COLORS.trigger)
  })

  it('returns approval color for approval step type', () => {
    expect(getStepTypeColor(FlowNodeType.APPROVAL)).toBe(STEP_TYPE_COLORS.approval)
  })

  it('returns logic color for condition, loop, converge', () => {
    expect(getStepTypeColor(FlowNodeType.CONDITION)).toBe(STEP_TYPE_COLORS.logic)
    expect(getStepTypeColor(FlowNodeType.LOOP)).toBe(STEP_TYPE_COLORS.logic)
    expect(getStepTypeColor(FlowNodeType.CONVERGE)).toBe(STEP_TYPE_COLORS.logic)
  })

  it('returns generic color for generic step type', () => {
    expect(getStepTypeColor(FlowNodeType.GENERIC)).toBe(STEP_TYPE_COLORS.generic)
  })

  it('returns actionScript color for task with script type', () => {
    expect(
      getStepTypeColor(FlowNodeType.TASK, {
        type: ExecutorTypeEnum.SCRIPT,
        id: 'test',
        parameters: {},
      } as Parameters<typeof getStepTypeColor>[1])
    ).toBe(STEP_TYPE_COLORS.actionScript)
  })

  it('returns actionAap color for task with aap_job_template type', () => {
    expect(
      getStepTypeColor(FlowNodeType.TASK, {
        type: ExecutorTypeEnum.AAP_JOB_TEMPLATE,
        id: 'test',
        parameters: {},
      } as Parameters<typeof getStepTypeColor>[1])
    ).toBe(STEP_TYPE_COLORS.actionAap)
  })

  it('SECURITY: rejects internal-only aap type from metadata override, falls back to agentic color', () => {
    // 'aap' is internal-only — metadata.__executorType: 'aap' from untrusted workflow JSON
    // must be rejected to prevent forcing arbitrary nodes to render with AAP styling
    expect(
      getStepTypeColor(FlowNodeType.TASK, {
        type: ExecutorTypeEnum.AGENTIC,
        id: 'test',
        parameters: {},
        metadata: { __executorType: DetectedExecutorType.AAP },
      } as Parameters<typeof getStepTypeColor>[1])
    ).toBe(STEP_TYPE_COLORS.actionAgentic)
  })

  it('returns actionAgentic color for task with agentic type', () => {
    expect(
      getStepTypeColor(FlowNodeType.TASK, {
        type: ExecutorTypeEnum.AGENTIC,
        id: 'test',
        parameters: {},
      } as Parameters<typeof getStepTypeColor>[1])
    ).toBe(STEP_TYPE_COLORS.actionAgentic)
  })

  it('returns actionHttpRequest for task with http_request type', () => {
    expect(
      getStepTypeColor(FlowNodeType.TASK, {
        type: ExecutorTypeEnum.HTTP_REQUEST,
        id: 'test',
        parameters: {},
      } as Parameters<typeof getStepTypeColor>[1])
    ).toBe(STEP_TYPE_COLORS.actionHttpRequest)
  })

  it('returns actionDefault for task-reversed with no data', () => {
    expect(getStepTypeColor(FlowNodeType.TASK_REVERSED)).toBe(STEP_TYPE_COLORS.actionDefault)
  })

  it('returns actionDefault for unknown step type', () => {
    expect(getStepTypeColor('unknown')).toBe(STEP_TYPE_COLORS.actionDefault)
  })
})

describe('getAddStepPanelColor', () => {
  it('returns undefined for trigger and trigger subtypes', () => {
    expect(getAddStepPanelColor(RegistryStepId.TRIGGER)).toBeUndefined()
    expect(getAddStepPanelColor(RegistryStepId.TRIGGER_MANUAL)).toBeUndefined()
    expect(getAddStepPanelColor(RegistryStepId.TRIGGER_SCHEDULED)).toBeUndefined()
  })

  it('returns logic color for logic and logic subtypes', () => {
    expect(getAddStepPanelColor(RegistryStepId.LOGIC)).toBe(STEP_TYPE_COLORS.logic)
    expect(getAddStepPanelColor(RegistryStepId.LOGIC_CONDITION)).toBe(STEP_TYPE_COLORS.logic)
    expect(getAddStepPanelColor(RegistryStepId.LOGIC_CONVERGE)).toBe(STEP_TYPE_COLORS.logic)
    expect(getAddStepPanelColor(RegistryStepId.LOGIC_LOOP)).toBe(STEP_TYPE_COLORS.logic)
  })

  it('returns approval color for approval', () => {
    expect(getAddStepPanelColor(RegistryStepId.APPROVAL)).toBe(STEP_TYPE_COLORS.approval)
  })

  it('returns actionScript color for action and action subtypes', () => {
    expect(getAddStepPanelColor(RegistryStepId.ACTION)).toBe(STEP_TYPE_COLORS.actionScript)
    expect(getAddStepPanelColor(RegistryStepId.ACTION_SCRIPT)).toBe(STEP_TYPE_COLORS.actionScript)
    expect(getAddStepPanelColor(RegistryStepId.ACTION_API)).toBe(STEP_TYPE_COLORS.actionScript)
  })

  it('returns actionAgentic color for agent', () => {
    expect(getAddStepPanelColor(RegistryStepId.AGENT)).toBe(STEP_TYPE_COLORS.actionAgentic)
  })

  it('returns actionAap color for AAP execution category', () => {
    expect(getAddStepPanelColor(RegistryStepId.AAP_EXECUTION)).toBe(STEP_TYPE_COLORS.actionAap)
  })

  it('returns undefined for empty or unknown registry id', () => {
    expect(getAddStepPanelColor('')).toBeUndefined()
    expect(getAddStepPanelColor('unknown')).toBeUndefined()
  })
})

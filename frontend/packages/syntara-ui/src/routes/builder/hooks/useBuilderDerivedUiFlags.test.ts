import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'

import { useBuilderDerivedUiFlags } from './useBuilderDerivedUiFlags'

describe('useBuilderDerivedUiFlags', () => {
  const emptyWorkflow = {
    triggers: [],
    workflow: { activities: [] },
  } as unknown as WorkflowDefinition

  const workflowWithTrigger = {
    triggers: [{ id: 't1', type: 'manual_trigger', parameters: {} }],
    workflow: { activities: [] },
  } as unknown as WorkflowDefinition

  it('treats add step panel as open when workflow has no triggers or steps', () => {
    const { result } = renderHook(() => useBuilderDerivedUiFlags(emptyWorkflow, false, null))

    expect(result.current.hasNoWorkflowSteps).toBe(true)
    expect(result.current.isAddStepPanelOpen).toBe(true)
  })

  it('reflects addStepPanelOpen when workflow has nodes', () => {
    const { result } = renderHook(() => useBuilderDerivedUiFlags(workflowWithTrigger, true, null))

    expect(result.current.hasNoWorkflowSteps).toBe(false)
    expect(result.current.isAddStepPanelOpen).toBe(true)
  })

  it('reports panel closed when addStepPanelOpen is false and workflow has content', () => {
    const { result } = renderHook(() => useBuilderDerivedUiFlags(workflowWithTrigger, false, null))

    expect(result.current.isAddStepPanelOpen).toBe(false)
  })
})

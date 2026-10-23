import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { NodeActionsContext, type NodeActionsContextValue } from '../../../../../routes/builder/NodeActionsContext'

import { StepMenuCategory, useNodeMenuActions } from './useNodeMenuActions'
import { useStepMenuActions } from './useStepMenuActions'

const mockDeleteElements = vi.fn()
vi.mock('@xyflow/react', () => ({
  useReactFlow: () => ({ deleteElements: mockDeleteElements }),
  useUpdateNodeInternals: () => vi.fn(),
}))

const mockShowError = vi.fn()
vi.mock('../../../../../providers/alerts', () => ({
  useAlerts: () => ({ showInfo: vi.fn(), showSuccess: vi.fn(), showError: mockShowError }),
}))

function withStepActions(value: NodeActionsContextValue) {
  return ({ children }: { children: ReactNode }) => (
    <NodeActionsContext.Provider value={value}>{children}</NodeActionsContext.Provider>
  )
}

describe('useNodeMenuActions compatibility wrapper', () => {
  it('maps legacy options to the shared step menu behavior', () => {
    const onViewDetails = vi.fn()
    const stepActions: NodeActionsContextValue = {
      onViewDetails,
      onReplace: vi.fn(),
      onDuplicate: vi.fn(),
      onRunStep: vi.fn(),
      onToggleDisabled: vi.fn(),
    }
    const wrapper = withStepActions(stepActions)
    const { result: legacyResult } = renderHook(
      () => useNodeMenuActions({ nodeId: 'step-1', nodeType: StepMenuCategory.ACTIVITY }),
      { wrapper }
    )
    const { result: stepResult } = renderHook(
      () => useStepMenuActions({ nodeId: 'step-1', stepCategory: StepMenuCategory.ACTIVITY }),
      { wrapper }
    )

    const describeActions = (actions: typeof legacyResult.current) =>
      actions.map(({ id, label, variant, separator }) => ({ id, label, variant, separator }))
    expect(describeActions(legacyResult.current)).toEqual(describeActions(stepResult.current))

    act(() => {
      legacyResult.current.find((action) => action.id === 'view-details')?.onClick()
    })
    expect(onViewDetails).toHaveBeenCalledWith('step-1')
  })
})

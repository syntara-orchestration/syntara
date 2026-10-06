import { act, renderHook } from '@testing-library/react'
import type React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { FlowNodeType } from '../../../constants'

import { useExecutionDetailInteractions } from './useExecutionDetailInteractions'

const mockNavigate = vi.fn()
const mockHandleNodeClick = vi.fn()
const mockSelectNode = vi.fn()

const approvalPanel = {
  open: vi.fn(),
  close: vi.fn(),
  panelOpen: false,
  approvalMessage: undefined,
  dismiss: vi.fn(),
}

const formPromptPanel = {
  open: vi.fn(),
  close: vi.fn(),
  panelOpen: false,
  dismiss: vi.fn(),
}

const nodeClick = {
  handleNodeClick: mockHandleNodeClick,
  selectNode: mockSelectNode,
  handleActivityRowClick: vi.fn(),
} as never

function renderInteractions(historyCardOpen = false) {
  return renderHook(() =>
    useExecutionDetailInteractions({
      executionId: 'exec-1',
      historyCardOpen,
      navigate: mockNavigate,
      nodeClick,
      approval: approvalPanel,
      formPromptPanel: formPromptPanel,
    })
  )
}

describe('useExecutionDetailInteractions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('opens form prompt panel and closes approval on waiting form prompt click', () => {
    const { result } = renderInteractions()
    const node = {
      id: 'form_a',
      type: FlowNodeType.FORM_PROMPT,
      data: { __executionState: { status: 'waiting' } },
    }

    act(() => {
      result.current.onCanvasNodeClick({} as React.MouseEvent, node)
    })

    expect(mockHandleNodeClick).toHaveBeenCalled()
    expect(formPromptPanel.open).toHaveBeenCalled()
    expect(approvalPanel.close).toHaveBeenCalled()
  })

  it('closes form prompt panel on non-waiting form prompt click', () => {
    const { result } = renderInteractions()
    const node = {
      id: 'form_a',
      type: FlowNodeType.FORM_PROMPT,
      data: { __executionState: { status: 'completed' } },
    }

    act(() => {
      result.current.onCanvasNodeClick({} as React.MouseEvent, node)
    })

    expect(formPromptPanel.close).toHaveBeenCalled()
  })

  it('opens approval panel on waiting approval click', () => {
    const { result } = renderInteractions()
    const node = {
      id: 'approve',
      type: FlowNodeType.APPROVAL,
      data: { __executionState: { status: 'waiting' } },
    }

    act(() => {
      result.current.onCanvasNodeClick({} as React.MouseEvent, node)
    })

    expect(approvalPanel.open).toHaveBeenCalled()
    expect(formPromptPanel.close).toHaveBeenCalled()
  })

  it('loads form prompt panel when a form prompt activity row is selected', () => {
    const handleActivityRowClick = vi.fn()
    const { result } = renderHook(() =>
      useExecutionDetailInteractions({
        executionId: 'exec-1',
        historyCardOpen: false,
        navigate: mockNavigate,
        nodeClick: {
          handleNodeClick: mockHandleNodeClick,
          selectNode: mockSelectNode,
          handleActivityRowClick,
        } as never,
        approval: approvalPanel,
        formPromptPanel: formPromptPanel,
        workflowDefinition: {
          workflow: { activities: [{ id: 'node-1', type: 'form_prompt', name: 'Step one' }] },
        },
      })
    )

    act(() => {
      result.current.onActivityRowSelect('node-1', 'Step one', 'node-1')
    })

    expect(mockSelectNode).toHaveBeenCalledWith('node-1', 'Step one')
    expect(handleActivityRowClick).toHaveBeenCalledWith('node-1')
    expect(formPromptPanel.open).toHaveBeenCalled()
    expect(approvalPanel.close).toHaveBeenCalled()
  })

  it('closes form prompt panel for non-form activity rows', () => {
    const { result } = renderInteractions()

    act(() => {
      result.current.onActivityRowSelect('node-1', 'Step one')
    })

    expect(formPromptPanel.close).toHaveBeenCalled()
  })

  it('closes side panels when opening history card', () => {
    const { result } = renderInteractions(false)

    act(() => {
      result.current.toggleHistoryCard()
    })

    expect(approvalPanel.close).toHaveBeenCalled()
    expect(formPromptPanel.close).toHaveBeenCalled()
    expect(mockNavigate).toHaveBeenCalledWith(
      expect.objectContaining({
        to: '/executions/$executionId',
        params: { executionId: 'exec-1' },
      })
    )
  })
})

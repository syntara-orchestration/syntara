import { act, renderHook } from '@testing-library/react'
import type React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FlowNodeType } from '../../../constants'

import { isFormPromptNode, isWaitingFormPromptNode, useExecutionFormPrompts } from './useExecutionFormPrompts'

const mockFetchFormPromptsForExecution = vi.fn()
const mockFetchPendingFromApi = vi.fn()
const mockClear = vi.fn()
const showInfo = vi.fn()
const showError = vi.fn()

const activityStates = new Map<string, { status: string; startedAt?: string }>()

vi.mock('./useFetchFormPromptsForExecution', () => ({
  useFetchFormPromptsForExecution: () => ({
    fetchPendingFormPrompts: mockFetchPendingFromApi,
    fetchFormPromptsForExecution: mockFetchFormPromptsForExecution,
    clear: mockClear,
    isLoading: false,
  }),
}))

vi.mock('../../../providers/alerts', () => ({
  useAlerts: () => ({
    showInfo,
    showError,
  }),
}))

vi.mock('../../workflows/stores/useExecutionStore', () => ({
  useExecutionStore: Object.assign(vi.fn(), {
    getState: () => ({ activityStates }),
  }),
}))

const workflowDefinition = {
  nodes: [
    { id: 'form_a', type: 'form_prompt' },
    { id: 'form_b', type: 'form_prompt' },
  ],
  edges: [{ from: 'form_a', to: 'form_b', from_port: 'submitted' }],
}

const waitingNode = {
  id: 'form_a',
  type: FlowNodeType.FORM_PROMPT,
  data: { __executionState: { status: 'waiting' } },
}

describe('isWaitingFormPromptNode', () => {
  it('returns true only for waiting form prompt nodes', () => {
    expect(isWaitingFormPromptNode(waitingNode)).toBe(true)

    expect(
      isWaitingFormPromptNode({
        id: 'form_a',
        type: FlowNodeType.FORM_PROMPT,
        data: { __executionState: { status: 'completed' } },
      })
    ).toBe(false)
  })

  it('returns false when execution state is missing', () => {
    expect(
      isWaitingFormPromptNode({
        id: 'form_a',
        type: FlowNodeType.FORM_PROMPT,
        data: {},
      })
    ).toBe(false)
  })
})

describe('isFormPromptNode', () => {
  it('returns true for form prompt node type', () => {
    expect(isFormPromptNode({ id: 'x', type: FlowNodeType.FORM_PROMPT, data: {} })).toBe(true)
    expect(isFormPromptNode({ id: 'x', type: FlowNodeType.APPROVAL, data: {} })).toBe(false)
  })
})

describe('useExecutionFormPrompts', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    activityStates.clear()
    mockFetchFormPromptsForExecution.mockResolvedValue([])
    mockFetchPendingFromApi.mockResolvedValue([])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('sorts prompts in workflow order when applying navigation list', async () => {
    mockFetchFormPromptsForExecution.mockResolvedValue([
      { id: 'fp-b', prompt_node_id: 'form_b', execution_id: 'exec-1', status: 'pending' },
      { id: 'fp-a', prompt_node_id: 'form_a', execution_id: 'exec-1', status: 'submitted' },
    ])

    const { result } = renderHook(() => useExecutionFormPrompts('exec-1', workflowDefinition))

    await act(async () => {
      await result.current.fetchFormPrompts()
    })

    expect(result.current.formPrompts.map((p) => p.id)).toEqual(['fp-a', 'fp-b'])
  })

  it('ignores clicks on non-waiting form prompt nodes', () => {
    const { result } = renderHook(() => useExecutionFormPrompts('exec-1', workflowDefinition))

    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, {
        id: 'form_a',
        type: FlowNodeType.FORM_PROMPT,
        data: { __executionState: { status: 'completed' } },
      })
    })

    expect(mockFetchFormPromptsForExecution).not.toHaveBeenCalled()
  })

  it('loads prompts when a waiting node is clicked', async () => {
    mockFetchFormPromptsForExecution.mockResolvedValue([
      {
        id: 'fp-1',
        prompt_node_id: 'form_a',
        execution_id: 'exec-1',
        project_id: 'p',
        name: 'A',
        status: 'pending',
        temporal_activity_id: 'form_a',
      },
    ])

    const { result } = renderHook(() => useExecutionFormPrompts('exec-1', workflowDefinition))

    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, waitingNode)
    })

    await act(async () => {
      await Promise.resolve()
    })

    expect(mockFetchFormPromptsForExecution).toHaveBeenCalled()
    expect(result.current.currentFormPrompt?.id).toBe('fp-1')
  })

  it('loads prompts from activity row selection', async () => {
    mockFetchFormPromptsForExecution.mockResolvedValue([
      {
        id: 'fp-1',
        prompt_node_id: 'form_a',
        execution_id: 'exec-1',
        project_id: 'p',
        name: 'A',
        status: 'pending',
        temporal_activity_id: 'form_a',
      },
    ])

    const { result } = renderHook(() => useExecutionFormPrompts('exec-1', workflowDefinition))

    act(() => {
      result.current.handleActivityRowClick('form_a')
    })

    await act(async () => {
      await Promise.resolve()
    })

    expect(mockFetchFormPromptsForExecution).toHaveBeenCalled()
  })

  it('shows info when no prompt matches the clicked node', async () => {
    mockFetchFormPromptsForExecution.mockResolvedValue([
      {
        id: 'fp-other',
        prompt_node_id: 'other',
        execution_id: 'exec-1',
        project_id: 'p',
        name: 'Other',
        status: 'pending',
        temporal_activity_id: 'other',
      },
    ])

    const { result } = renderHook(() => useExecutionFormPrompts('exec-1', workflowDefinition))

    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, waitingNode)
    })

    await act(async () => {
      await Promise.resolve()
    })

    expect(showInfo).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Form prompt not found',
        description: 'This form prompt has been resolved or is no longer available for this step.',
      })
    )
  })

  it('describes still-creating prompt when canvas is waiting but list is empty', async () => {
    vi.useFakeTimers()
    activityStates.set('form_a', { status: 'waiting' })
    mockFetchFormPromptsForExecution.mockResolvedValue([])

    const { result } = renderHook(() => useExecutionFormPrompts('exec-1', workflowDefinition))

    act(() => {
      result.current.handleActivityRowClick('form_a')
    })

    await act(async () => {
      await vi.runAllTimersAsync()
      await Promise.resolve()
    })

    expect(showInfo).toHaveBeenCalledWith(
      expect.objectContaining({
        description: 'The form prompt is still being created for this step. Wait a moment and try again.',
      })
    )
  })

  it('shows error when execution id is missing during load', () => {
    const { result } = renderHook(() => useExecutionFormPrompts(undefined, workflowDefinition))

    act(() => {
      result.current.handleActivityRowClick('form_a')
    })

    expect(showError).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Failed to load form prompt',
      })
    )
  })

  it('shows fetch error once per node and message', async () => {
    mockFetchFormPromptsForExecution.mockRejectedValue(new Error('network down'))

    const { result } = renderHook(() => useExecutionFormPrompts('exec-1', workflowDefinition))

    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, waitingNode)
    })

    await act(async () => {
      await Promise.resolve()
    })

    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, waitingNode)
    })

    await act(async () => {
      await Promise.resolve()
    })

    expect(showError).toHaveBeenCalledTimes(1)
  })

  it('clamps navigateToIndex to list bounds', () => {
    const { result } = renderHook(() => useExecutionFormPrompts('exec-1', workflowDefinition))

    act(() => {
      result.current.setFormPromptsAndIndex(
        [
          {
            id: 'fp-1',
            prompt_node_id: 'form_a',
            execution_id: 'exec-1',
            project_id: 'p',
            name: 'A',
            status: 'pending',
            temporal_activity_id: '',
          },
        ],
        0
      )
    })

    act(() => {
      result.current.navigateToIndex(99)
    })
    expect(result.current.currentIndex).toBe(0)

    act(() => {
      result.current.navigateToIndex(-5)
    })
    expect(result.current.currentIndex).toBe(0)
  })

  it('clears prompts when execution id changes', () => {
    const { result, rerender } = renderHook(
      ({ executionId }: { executionId: string }) => useExecutionFormPrompts(executionId, workflowDefinition),
      { initialProps: { executionId: 'exec-1' } }
    )

    act(() => {
      result.current.setFormPromptsAndIndex(
        [
          {
            id: 'fp-1',
            prompt_node_id: 'form_a',
            execution_id: 'exec-1',
            project_id: 'proj-1',
            name: 'Form A',
            status: 'pending',
            temporal_activity_id: '',
          },
        ],
        0
      )
    })

    rerender({ executionId: 'exec-2' })

    expect(result.current.formPrompts).toEqual([])
    expect(result.current.currentIndex).toBe(0)
  })

  it('retries fetch while canvas node remains waiting', async () => {
    vi.useFakeTimers()
    activityStates.set('form_a', { status: 'waiting' })
    mockFetchFormPromptsForExecution.mockResolvedValueOnce([]).mockResolvedValueOnce([
      {
        id: 'fp-1',
        prompt_node_id: 'form_a',
        execution_id: 'exec-1',
        project_id: 'p',
        name: 'A',
        status: 'pending',
        temporal_activity_id: 'form_a',
      },
    ])

    const { result } = renderHook(() => useExecutionFormPrompts('exec-1', workflowDefinition))

    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, waitingNode)
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(600)
      await Promise.resolve()
    })

    expect(mockFetchFormPromptsForExecution).toHaveBeenCalledTimes(2)
    expect(result.current.currentFormPrompt?.id).toBe('fp-1')
  })
})

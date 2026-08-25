import type { Approval } from '@syntara/contracts'
import { renderHook, act } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

import { useExecutionStore } from '../../workflows/stores/useExecutionStore'

import { useExecutionApprovalPanel } from './useExecutionApprovalPanel'

vi.mock('../../workflows/stores/useExecutionStore', () => {
  const activityStates = new Map<string, { status: string }>()
  const subscribers = new Set<() => void>()

  return {
    useExecutionStore: Object.assign(
      vi.fn(() => ({ activityStates })),
      {
        getState: () => ({ activityStates }),
        subscribe: (fn: () => void) => {
          subscribers.add(fn)
          return () => subscribers.delete(fn)
        },
        __test__: {
          activityStates,
          subscribers,
          setStatus: (nodeId: string, status: string) => {
            activityStates.set(nodeId, { status })
            for (const fn of subscribers) fn()
          },
          clear: () => {
            activityStates.clear()
            subscribers.clear()
          },
        },
      }
    ),
  }
})

const storeHelpers = (
  useExecutionStore as unknown as {
    __test__: {
      activityStates: Map<string, { status: string }>
      subscribers: Set<() => void>
      setStatus: (nodeId: string, status: string) => void
      clear: () => void
    }
  }
).__test__

const mockApproval: Approval = {
  id: 'approval-1',
  project_id: 'project-1',
  name: 'Test Approval',
  status: 'pending',
  execution_id: 'exec-1',
  approval_node_id: 'node-1',
  created_at: '2026-01-01T00:00:00Z',
  next_step_approved: { id: 'step-a', name: 'Approved Step', type: 'task' },
  workflow_context: {
    workflow_id: 'wfv-1',
    workflow_name: 'Test Workflow',
    inputs: {},
  },
}

const mockFetchApprovals = vi.fn()
const mockSetApprovalsAndIndex = vi.fn()
const mockClearApprovals = vi.fn()

vi.mock('./useFetchApprovalForUrlParam', () => ({
  useFetchApprovalForUrlParam: vi.fn(() => undefined),
}))

vi.mock('./useAutoApprovalDetection', () => ({
  useAutoApprovalDetection: vi.fn(),
}))

vi.mock('../../../providers/alerts', () => ({
  useAlerts: vi.fn(() => ({
    showError: vi.fn(),
    showSuccess: vi.fn(),
    showInfo: vi.fn(),
    showWarning: vi.fn(),
  })),
}))

function makeNodeClick(currentApproval: Approval | null = null, approvals: Approval[] = []) {
  return {
    fetchApprovals: mockFetchApprovals,
    setApprovalsAndIndex: mockSetApprovalsAndIndex,
    clearApprovals: mockClearApprovals,
    approvals,
    currentIndex: 0,
    currentApproval,
    selectedNodeId: null,
    setSelectedNodeId: vi.fn(),
    isFetching: false,
    nodeExecution: undefined,
  } as never
}

describe('useExecutionApprovalPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    storeHelpers.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
    storeHelpers.clear()
  })

  it('starts with panel closed', () => {
    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', makeNodeClick(), undefined))
    expect(result.current.panelOpen).toBe(false)
  })

  it('opens panel via open()', () => {
    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', makeNodeClick(), undefined))

    act(() => result.current.open())
    expect(result.current.panelOpen).toBe(true)
  })

  it('closes panel via close()', () => {
    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', makeNodeClick(), undefined))

    act(() => result.current.open())
    expect(result.current.panelOpen).toBe(true)

    act(() => result.current.close())
    expect(result.current.panelOpen).toBe(false)
  })

  it('dismiss() closes panel when no more approvals remain', async () => {
    mockFetchApprovals.mockResolvedValue([]) // No more pending approvals
    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', makeNodeClick(), undefined))

    act(() => result.current.open())

    act(() => result.current.dismiss())
    await act(async () => {
      await vi.runAllTimersAsync()
    })

    expect(result.current.panelOpen).toBe(false)
    expect(mockClearApprovals).toHaveBeenCalledOnce()
  })

  it('dismiss() keeps panel open and navigates when approvals remain', async () => {
    const remainingApprovals = [
      { ...mockApproval, id: 'approval-2', name: 'Second Approval' },
      { ...mockApproval, id: 'approval-3', name: 'Third Approval' },
    ]
    mockFetchApprovals.mockResolvedValue(remainingApprovals)
    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', makeNodeClick(), undefined))

    act(() => result.current.open())

    act(() => result.current.dismiss())
    await act(async () => {
      await vi.runAllTimersAsync()
    })

    expect(result.current.panelOpen).toBe(true)
    expect(mockSetApprovalsAndIndex).toHaveBeenCalledWith(remainingApprovals, 0)
  })

  it('opens panel when URL approval is fetched', async () => {
    const { useFetchApprovalForUrlParam } = await import('./useFetchApprovalForUrlParam')
    vi.mocked(useFetchApprovalForUrlParam).mockReturnValue(mockApproval)
    mockFetchApprovals.mockResolvedValue([mockApproval])

    const { result } = renderHook(() =>
      useExecutionApprovalPanel('exec-1', '?approval=approval-1', makeNodeClick(), undefined)
    )

    await act(async () => {
      await vi.runAllTimersAsync()
    })

    expect(result.current.panelOpen).toBe(true)
    expect(mockFetchApprovals).toHaveBeenCalled()
    expect(mockSetApprovalsAndIndex).toHaveBeenCalledWith([mockApproval], 0)
  })

  it('auto-detection callback opens panel', async () => {
    const { useAutoApprovalDetection } = await import('./useAutoApprovalDetection')

    let capturedCallback: ((a: Approval) => void) | undefined
    vi.mocked(useAutoApprovalDetection).mockImplementation((opts: { onApprovalDetected: (a: Approval) => void }) => {
      capturedCallback = opts.onApprovalDetected
    })

    mockFetchApprovals.mockResolvedValue([mockApproval])

    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', makeNodeClick(), undefined))

    expect(capturedCallback).toBeDefined()

    // Call the callback and wait for all async state updates to complete
    await act(async () => {
      capturedCallback!(mockApproval)
      await vi.runAllTimersAsync()
    })

    // Panel should now be open
    expect(result.current.panelOpen).toBe(true)
    expect(mockFetchApprovals).toHaveBeenCalled()
    expect(mockSetApprovalsAndIndex).toHaveBeenCalledWith([mockApproval], 0)
  })

  it('returns approvalMessage from workflow definition', () => {
    const nodeClick = makeNodeClick(mockApproval, [mockApproval])
    const wfDef = {
      nodes: [{ id: 'node-1', config: { prompt: 'Deploy to production?' } }],
    }

    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', nodeClick, wfDef))

    expect(result.current.approvalMessage).toBe('Deploy to production?')
  })

  it('returns approvalMessage when approval_node_id has a loop-iteration suffix', () => {
    const loopApproval = { ...mockApproval, approval_node_id: 'node-1_iter_0' }
    const nodeClick = makeNodeClick(loopApproval, [loopApproval])
    const wfDef = {
      nodes: [{ id: 'node-1', config: { prompt: 'Approve this server?' } }],
    }

    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', nodeClick, wfDef))

    expect(result.current.approvalMessage).toBe('Approve this server?')
  })

  it('returns approvalMessage from v2 parameters.prompt', () => {
    const nodeClick = makeNodeClick(mockApproval, [mockApproval])
    const wfDef = {
      nodes: [{ id: 'node-1', parameters: { prompt: 'Message will go here. User inputs it' } }],
    }

    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', nodeClick, wfDef))

    expect(result.current.approvalMessage).toBe('Message will go here. User inputs it')
  })

  it('prefers parameters.prompt over config.prompt', () => {
    const nodeClick = makeNodeClick(mockApproval, [mockApproval])
    const wfDef = {
      nodes: [
        {
          id: 'node-1',
          parameters: { prompt: 'From parameters' },
          config: { prompt: 'From config' },
        },
      ],
    }

    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', nodeClick, wfDef))

    expect(result.current.approvalMessage).toBe('From parameters')
  })

  it('returns undefined approvalMessage when no matching node', () => {
    const nodeClick = makeNodeClick(mockApproval, [mockApproval])
    const wfDef = {
      nodes: [{ id: 'other-node', config: { prompt: 'Something else' } }],
    }

    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', nodeClick, wfDef))

    expect(result.current.approvalMessage).toBeUndefined()
  })

  it('returns undefined approvalMessage when no workflow definition', () => {
    const { result } = renderHook(() =>
      useExecutionApprovalPanel('exec-1', '', makeNodeClick(mockApproval, [mockApproval]), undefined)
    )

    expect(result.current.approvalMessage).toBeUndefined()
  })

  it('returns undefined approvalMessage when workflow definition has no nodes', () => {
    const { result } = renderHook(() =>
      useExecutionApprovalPanel('exec-1', '', makeNodeClick(mockApproval, [mockApproval]), { nodes: [] })
    )

    expect(result.current.approvalMessage).toBeUndefined()
  })

  it('returns undefined approvalMessage when node has no config', () => {
    const nodeClick = makeNodeClick(mockApproval, [mockApproval])
    const wfDef = {
      nodes: [{ id: 'node-1' }], // No config
    }

    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', nodeClick, wfDef))

    expect(result.current.approvalMessage).toBeUndefined()
  })

  it('returns undefined approvalMessage when config has no prompt', () => {
    const nodeClick = makeNodeClick(mockApproval, [mockApproval])
    const wfDef = {
      nodes: [{ id: 'node-1', config: {} }], // Empty config
    }

    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', nodeClick, wfDef))

    expect(result.current.approvalMessage).toBeUndefined()
  })

  it('dismiss() closes panel when fetch fails', async () => {
    mockFetchApprovals.mockRejectedValue(new Error('Fetch failed'))
    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', makeNodeClick(), undefined))

    act(() => result.current.open())
    expect(result.current.panelOpen).toBe(true)

    act(() => result.current.dismiss())
    await act(async () => {
      await vi.runAllTimersAsync()
    })

    expect(result.current.panelOpen).toBe(false)
    expect(mockClearApprovals).toHaveBeenCalledOnce()
  })

  it('handles URL approval not in fetched list (defaults to first approval)', async () => {
    const { useFetchApprovalForUrlParam } = await import('./useFetchApprovalForUrlParam')
    const urlApproval = { ...mockApproval, id: 'url-approval-not-in-list' }
    vi.mocked(useFetchApprovalForUrlParam).mockReturnValue(urlApproval as Approval)
    mockFetchApprovals.mockResolvedValue([mockApproval]) // URL approval not in the fetched list

    const { result } = renderHook(() =>
      useExecutionApprovalPanel('exec-1', '?approval=url-approval-not-in-list', makeNodeClick(), undefined)
    )

    await act(async () => {
      await vi.runAllTimersAsync()
    })

    expect(result.current.panelOpen).toBe(true)
    expect(mockSetApprovalsAndIndex).toHaveBeenCalledWith([mockApproval], 0)
  })

  it('shows error alert when URL approval fetch fails', async () => {
    const { useFetchApprovalForUrlParam } = await import('./useFetchApprovalForUrlParam')
    const { useAlerts } = await import('../../../providers/alerts')
    const showError = vi.fn()
    vi.mocked(useAlerts).mockReturnValueOnce({
      showError,
      showSuccess: vi.fn(),
      showInfo: vi.fn(),
      showWarning: vi.fn(),
    } as never)

    vi.mocked(useFetchApprovalForUrlParam).mockReturnValue(mockApproval)
    mockFetchApprovals.mockRejectedValue(new Error('Failed to fetch'))

    renderHook(() => useExecutionApprovalPanel('exec-1', '?approval=approval-1', makeNodeClick(), undefined))

    await act(async () => {
      await vi.runAllTimersAsync()
    })

    expect(showError).toHaveBeenCalledWith({
      title: 'Failed to load approval',
      description: 'Could not fetch approval details. Please try again.',
    })
  })

  it('auto-detection shows error when fetch fails', async () => {
    const { useAutoApprovalDetection } = await import('./useAutoApprovalDetection')
    const { useAlerts } = await import('../../../providers/alerts')
    const showError = vi.fn()
    vi.mocked(useAlerts).mockReturnValueOnce({
      showError,
      showSuccess: vi.fn(),
      showInfo: vi.fn(),
      showWarning: vi.fn(),
    } as never)

    let capturedCallback: ((a: Approval) => void) | undefined
    vi.mocked(useAutoApprovalDetection).mockImplementation((opts: { onApprovalDetected: (a: Approval) => void }) => {
      capturedCallback = opts.onApprovalDetected
    })

    mockFetchApprovals.mockRejectedValue(new Error('Fetch failed'))

    renderHook(() => useExecutionApprovalPanel('exec-1', '', makeNodeClick(), undefined))

    await act(async () => {
      capturedCallback!(mockApproval)
      await vi.runAllTimersAsync()
    })

    expect(showError).toHaveBeenCalledWith({
      title: 'Failed to load approval',
      description: 'Could not fetch approval details. Please try again.',
    })
  })

  it('auto-detection sets index when detected approval not in list (defaults to first)', async () => {
    const { useAutoApprovalDetection } = await import('./useAutoApprovalDetection')

    let capturedCallback: ((a: Approval) => void) | undefined
    vi.mocked(useAutoApprovalDetection).mockImplementation((opts: { onApprovalDetected: (a: Approval) => void }) => {
      capturedCallback = opts.onApprovalDetected
    })

    const detectedApproval = { ...mockApproval, id: 'detected-not-in-list' }
    mockFetchApprovals.mockResolvedValue([mockApproval]) // detected approval not in list

    renderHook(() => useExecutionApprovalPanel('exec-1', '', makeNodeClick(), undefined))

    await act(async () => {
      capturedCallback!(detectedApproval as Approval)
      await vi.runAllTimersAsync()
    })

    expect(mockSetApprovalsAndIndex).toHaveBeenCalledWith([mockApproval], 0)
  })

  it('auto-closes panel when approvals transition from some to none', async () => {
    const nodeClick = makeNodeClick(mockApproval, [mockApproval])
    const { result, rerender } = renderHook(
      ({ nc }: { nc: ReturnType<typeof makeNodeClick> }) => useExecutionApprovalPanel('exec-1', '', nc, undefined),
      {
        initialProps: { nc: nodeClick },
      }
    )

    act(() => result.current.open())
    expect(result.current.panelOpen).toBe(true)

    // Simulate approvals going from 1 to 0
    const emptyNodeClick = makeNodeClick(null, [])
    rerender({ nc: emptyNodeClick })

    await act(async () => {
      await vi.runAllTimersAsync()
    })

    expect(result.current.panelOpen).toBe(false)
    expect(mockClearApprovals).toHaveBeenCalled()
  })

  it('does not auto-close when panel was already closed', async () => {
    const nodeClick = makeNodeClick(mockApproval, [mockApproval])
    const { rerender } = renderHook(
      ({ nc }: { nc: ReturnType<typeof makeNodeClick> }) => useExecutionApprovalPanel('exec-1', '', nc, undefined),
      {
        initialProps: { nc: nodeClick },
      }
    )

    // Panel starts closed
    const emptyNodeClick = makeNodeClick(null, [])
    rerender({ nc: emptyNodeClick })

    await act(async () => {
      await vi.runAllTimersAsync()
    })

    // clearApprovals should not be called because panel was never open
    expect(mockClearApprovals).not.toHaveBeenCalled()
  })

  it('resolves approval message from workflow.activities when nodes is missing', () => {
    const nodeClick = makeNodeClick(mockApproval, [mockApproval])
    const wfDef = {
      workflow: {
        activities: [{ id: 'node-1', parameters: { prompt: 'Approve deployment?' } }],
      },
    }

    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', nodeClick, wfDef))

    expect(result.current.approvalMessage).toBe('Approve deployment?')
  })

  it('returns undefined approvalMessage when config.prompt is not a string', () => {
    const nodeClick = makeNodeClick(mockApproval, [mockApproval])
    const wfDef = {
      nodes: [{ id: 'node-1', config: { prompt: 123 } }], // prompt is a number
    }

    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', nodeClick, wfDef))

    expect(result.current.approvalMessage).toBeUndefined()
  })

  it('returns undefined approvalMessage when config is not an object', () => {
    const nodeClick = makeNodeClick(mockApproval, [mockApproval])
    const wfDef = {
      nodes: [{ id: 'node-1', config: 'invalid' }], // config is a string
    }

    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', nodeClick, wfDef))

    expect(result.current.approvalMessage).toBeUndefined()
  })

  it('returns undefined approvalMessage when config is null', () => {
    const nodeClick = makeNodeClick(mockApproval, [mockApproval])
    const wfDef = {
      nodes: [{ id: 'node-1', config: null }],
    }

    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', nodeClick, wfDef))

    expect(result.current.approvalMessage).toBeUndefined()
  })

  it('clears handledApprovalId when URL param is removed', async () => {
    const { useFetchApprovalForUrlParam } = await import('./useFetchApprovalForUrlParam')
    vi.mocked(useFetchApprovalForUrlParam).mockReturnValue(mockApproval)
    mockFetchApprovals.mockResolvedValue([mockApproval])

    const { result, rerender } = renderHook(
      ({ search }: { search: string }) => useExecutionApprovalPanel('exec-1', search, makeNodeClick(), undefined),
      {
        initialProps: { search: '?approval=approval-1' },
      }
    )

    await act(async () => {
      await vi.runAllTimersAsync()
    })

    // Panel should be open after URL approval loads
    expect(result.current.panelOpen).toBe(true)

    // Now remove the URL param
    vi.mocked(useFetchApprovalForUrlParam).mockReturnValue(undefined)

    rerender({ search: '' })
    await act(async () => {
      await vi.runAllTimersAsync()
    })

    // handledApprovalId should be cleared - verify no error thrown
    expect(result.current).toBeDefined()
  })

  it('auto-dismisses panel when activity transitions to terminal state', async () => {
    mockFetchApprovals.mockResolvedValue([])
    const nodeClick = makeNodeClick(mockApproval, [mockApproval])

    // Set activity to waiting state initially
    storeHelpers.setStatus('node-1', 'waiting')

    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', nodeClick, undefined))

    act(() => result.current.open())
    expect(result.current.panelOpen).toBe(true)

    // Simulate the activity transitioning to "failed" (e.g., timeout)
    await act(async () => {
      storeHelpers.setStatus('node-1', 'failed')
      await vi.runAllTimersAsync()
    })

    // Panel should auto-close because dismiss() was called and no pending approvals remain
    expect(result.current.panelOpen).toBe(false)
    expect(mockClearApprovals).toHaveBeenCalled()
  })

  it('does not auto-dismiss when activity is still waiting', async () => {
    const nodeClick = makeNodeClick(mockApproval, [mockApproval])

    storeHelpers.setStatus('node-1', 'waiting')

    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', nodeClick, undefined))

    act(() => result.current.open())
    expect(result.current.panelOpen).toBe(true)

    // Activity stays in waiting — panel should remain open
    await act(async () => {
      await vi.runAllTimersAsync()
    })

    expect(result.current.panelOpen).toBe(true)
  })

  it('auto-dismisses using this approval iteration activity key', async () => {
    mockFetchApprovals.mockResolvedValue([])
    const loopApproval = { ...mockApproval, loop_iteration_path: [2] }
    const nodeClick = makeNodeClick(loopApproval, [loopApproval])

    storeHelpers.setStatus('node-1#iter-2', 'waiting')

    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', nodeClick, undefined))

    act(() => result.current.open())
    expect(result.current.panelOpen).toBe(true)

    await act(async () => {
      storeHelpers.setStatus('node-1#iter-2', 'failed')
      await vi.runAllTimersAsync()
    })

    expect(result.current.panelOpen).toBe(false)
    expect(mockClearApprovals).toHaveBeenCalled()
  })

  it('does not dismiss a nested pass when an earlier canvas record is already completed', async () => {
    mockFetchApprovals.mockResolvedValue([])
    const nestedApproval = { ...mockApproval, loop_iteration_path: [1, 0] }
    const nodeClick = makeNodeClick(nestedApproval, [nestedApproval])

    storeHelpers.setStatus('node-1', 'completed')
    storeHelpers.setStatus('node-1#iter-0', 'completed')
    storeHelpers.setStatus('node-1#iter-3', 'waiting')

    const { result } = renderHook(() => useExecutionApprovalPanel('exec-1', '', nodeClick, undefined))

    act(() => result.current.open())
    expect(result.current.panelOpen).toBe(true)

    await act(async () => {
      storeHelpers.setStatus('node-1', 'completed')
      await vi.runAllTimersAsync()
    })

    expect(result.current.panelOpen).toBe(true)
    expect(mockClearApprovals).not.toHaveBeenCalled()

    await act(async () => {
      storeHelpers.setStatus('node-1#iter-3', 'failed')
      await vi.runAllTimersAsync()
    })

    expect(result.current.panelOpen).toBe(false)
    expect(mockClearApprovals).toHaveBeenCalled()
  })
})

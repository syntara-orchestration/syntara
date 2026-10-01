import type { FormsAPI } from '@syntara/contracts'
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useExecutionFormPromptPanel } from './useExecutionFormPromptPanel'

vi.mock('../../workflows/stores/useExecutionStore', () => {
  const activityStates = new Map<string, { status: string }>()
  const subscribers = new Set<() => void>()

  return {
    useExecutionStore: Object.assign(vi.fn(), {
      getState: () => ({ activityStates }),
      subscribe: (fn: () => void) => {
        subscribers.add(fn)
        return () => subscribers.delete(fn)
      },
    }),
  }
})

const mockFetchPending = vi.fn()
const mockFetchFormPrompts = vi.fn()
const mockSetFormPromptsAndIndex = vi.fn()
const mockClearFormPrompts = vi.fn()

vi.mock('./useFetchFormPromptForUrlParam', () => ({
  useFetchFormPromptForUrlParam: vi.fn(() => ({
    formPrompt: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  })),
}))

vi.mock('./useAutoWaitingNodeDetection', () => ({
  useAutoWaitingNodeDetection: vi.fn(),
}))

vi.mock('../../../providers/alerts', () => ({
  useAlerts: () => ({
    showError: vi.fn(),
    showSuccess: vi.fn(),
    showInfo: vi.fn(),
    showWarning: vi.fn(),
  }),
}))

type FormPromptSummary = FormsAPI.components['schemas']['FormPromptSummary']

const mockSummary: FormPromptSummary = {
  id: 'fp-1',
  execution_id: 'exec-1',
  project_id: 'proj-1',
  prompt_node_id: 'form_a',
  name: 'Form A',
  status: 'pending',
  temporal_activity_id: 'act-1',
}

function makeNodeClick(overrides: Record<string, unknown> = {}) {
  return {
    fetchPendingFormPrompts: mockFetchPending,
    fetchFormPrompts: mockFetchFormPrompts,
    setFormPromptsAndIndex: mockSetFormPromptsAndIndex,
    clearFormPrompts: mockClearFormPrompts,
    currentFormPrompt: null,
    formPrompts: [],
    ...overrides,
  } as never
}

describe('useExecutionFormPromptPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    mockFetchPending.mockResolvedValue([])
    mockFetchFormPrompts.mockResolvedValue([])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts with panel closed', () => {
    const { result } = renderHook(() => useExecutionFormPromptPanel('exec-1', '', makeNodeClick(), undefined))
    expect(result.current.panelOpen).toBe(false)
  })

  it('opens and closes via open/close', () => {
    const { result } = renderHook(() => useExecutionFormPromptPanel('exec-1', '', makeNodeClick(), undefined))

    act(() => result.current.open())
    expect(result.current.panelOpen).toBe(true)

    act(() => result.current.close())
    expect(result.current.panelOpen).toBe(false)
  })

  it('opens panel from URL param in useEffect', async () => {
    const { useFetchFormPromptForUrlParam } = await import('./useFetchFormPromptForUrlParam')
    vi.mocked(useFetchFormPromptForUrlParam).mockReturnValue({
      formPrompt: {
        id: 'fp-1',
        execution_id: 'exec-1',
        project_id: 'proj-1',
        prompt_node_id: 'form_a',
        name: 'Form A',
        status: 'pending',
        form_definition: { fields: [] },
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })
    mockFetchPending.mockResolvedValue([mockSummary])

    const { result } = renderHook(() =>
      useExecutionFormPromptPanel('exec-1', '?form_prompt=fp-1', makeNodeClick(), undefined)
    )

    await act(async () => {
      await Promise.resolve()
    })

    expect(result.current.panelOpen).toBe(true)
    expect(mockFetchPending).toHaveBeenCalled()
    expect(mockSetFormPromptsAndIndex).toHaveBeenCalledWith([mockSummary], 0)
  })

  it('dismiss closes panel when no pending prompts remain', async () => {
    mockFetchPending.mockResolvedValue([])
    const { result } = renderHook(() => useExecutionFormPromptPanel('exec-1', '', makeNodeClick(), undefined))

    act(() => result.current.open())
    act(() => result.current.dismiss())

    await act(async () => {
      await Promise.resolve()
    })

    expect(result.current.panelOpen).toBe(false)
    expect(mockClearFormPrompts).toHaveBeenCalled()
  })

  it('closes panel when execution id changes', () => {
    const { result, rerender } = renderHook(
      ({ executionId }: { executionId: string }) =>
        useExecutionFormPromptPanel(executionId, '', makeNodeClick(), undefined),
      { initialProps: { executionId: 'exec-1' } }
    )

    act(() => result.current.open())
    rerender({ executionId: 'exec-2' })

    expect(result.current.panelOpen).toBe(false)
  })

  it('auto-detection opens panel with fetched prompts', async () => {
    const { useAutoWaitingNodeDetection } = await import('./useAutoWaitingNodeDetection')
    let onDetected: ((item: FormPromptSummary) => void) | undefined
    vi.mocked(useAutoWaitingNodeDetection).mockImplementation(
      (opts: { onDetected: (item: FormPromptSummary) => void }) => {
        onDetected = opts.onDetected
      }
    )
    mockFetchFormPrompts.mockResolvedValue([mockSummary])

    const { result } = renderHook(() => useExecutionFormPromptPanel('exec-1', '', makeNodeClick(), undefined))

    await act(async () => {
      onDetected?.(mockSummary)
      await Promise.resolve()
    })

    expect(result.current.panelOpen).toBe(true)
    expect(mockSetFormPromptsAndIndex).toHaveBeenCalledWith([mockSummary], 0)
  })

  it('builds single-item navigation when URL prompt is missing from pending list', async () => {
    const { useFetchFormPromptForUrlParam } = await import('./useFetchFormPromptForUrlParam')
    vi.mocked(useFetchFormPromptForUrlParam).mockReturnValue({
      formPrompt: {
        id: 'fp-url',
        execution_id: 'exec-1',
        project_id: 'proj-1',
        prompt_node_id: 'form_url',
        name: 'URL Form',
        status: 'pending',
        form_definition: { fields: [] },
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })
    mockFetchPending.mockResolvedValue([])

    renderHook(() => useExecutionFormPromptPanel('exec-1', '?form_prompt=fp-url', makeNodeClick(), undefined))

    await act(async () => {
      await Promise.resolve()
    })

    expect(mockSetFormPromptsAndIndex).toHaveBeenCalledWith(
      [
        expect.objectContaining({
          id: 'fp-url',
          prompt_node_id: 'form_url',
        }),
      ],
      0
    )
  })

  it('auto-closes panel when prompts list becomes empty', async () => {
    const nodeClick = makeNodeClick({ formPrompts: [mockSummary] })
    const { result, rerender } = renderHook(
      ({ nc }: { nc: ReturnType<typeof makeNodeClick> }) => useExecutionFormPromptPanel('exec-1', '', nc, undefined),
      { initialProps: { nc: nodeClick } }
    )

    act(() => result.current.open())
    rerender({ nc: makeNodeClick({ formPrompts: [] }) })

    await act(async () => {
      await vi.runAllTimersAsync()
    })

    expect(result.current.panelOpen).toBe(false)
    expect(mockClearFormPrompts).toHaveBeenCalled()
  })
})

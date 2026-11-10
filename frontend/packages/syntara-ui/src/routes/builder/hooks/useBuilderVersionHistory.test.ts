import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useBuilderVersionHistory } from './useBuilderVersionHistory'

const mockLoadWorkflowWithEdges = vi.fn()
const mockRestoreMutate = vi.fn()
const mockRefetch = vi.fn().mockResolvedValue({})

const mockVersions = [
  { version: 2, status: 'draft', workflow_definition: { name: 'v2' } },
  { version: 1, status: 'published', workflow_definition: { name: 'v1' } },
]

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: () => ({
    loadWorkflowWithEdges: mockLoadWorkflowWithEdges,
    markClean: vi.fn(),
  }),
}))

vi.mock('./useVersionHistory', () => ({
  useVersionHistory: () => ({
    filteredVersions: mockVersions,
    statusFilter: null,
    setStatusFilter: vi.fn(),
    exportVersion: vi.fn(),
    openInNewWindow: vi.fn(),
    publishVersion: vi.fn(),
    restoreMutation: { mutate: mockRestoreMutate, isPending: false },
    versionsQuery: { refetch: mockRefetch },
    paginationFooterProps: {
      page: 1,
      perPage: 20,
      total: null,
      hasNext: false,
      onPrev: vi.fn(),
      onNext: vi.fn(),
      onPerPageChange: vi.fn(),
    },
  }),
}))

vi.mock('../../../client', () => ({
  workflowClient: {
    useQuery: vi.fn((_method: string, _path: string, _params: unknown, opts: { enabled: boolean }) => ({
      data: opts.enabled
        ? {
            created_at: '2026-05-19T14:30:00.000Z',
            change_description: 'Bug fix',
            name: 'Release 1.0',
            workflow_definition: {
              schema_version: '2.0.0',
              name: 'test',
              triggers: [],
              nodes: [],
              edges: [],
            },
          }
        : undefined,
    })),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../utils/processExistingWorkflow', () => ({
  convertV2Definition: () => ({
    flattenedActivities: [],
    edges: [],
    triggers: [],
  }),
  parseNodePositions: () => ({}),
}))

function makeWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

function createDefaultParams() {
  return {
    workflowId: 'wf-1' as string | null,
    isNew: false,
    workflow: {
      name: 'test-workflow',
      version: {
        workflow_definition: {
          schema_version: '2.0.0' as const,
          name: 'current',
          triggers: [],
          nodes: [],
          edges: [],
        },
      },
    } as unknown as Parameters<typeof useBuilderVersionHistory>[0]['workflow'],
    viewingVersion: null as number | null,
    dispatch: vi.fn(),
    showSuccess: vi.fn(),
    showError: vi.fn(),
    searchParams: new URLSearchParams(),
    setSearchParams: vi.fn(),
  }
}

describe('useBuilderVersionHistory', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  })

  it('returns filtered versions from useVersionHistory', () => {
    const params = createDefaultParams()
    const { result } = renderHook(() => useBuilderVersionHistory(params), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.filteredVersions).toEqual(mockVersions)
  })

  it('exposes paginationFooterProps from useVersionHistory', () => {
    const params = createDefaultParams()
    const { result } = renderHook(() => useBuilderVersionHistory(params), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.paginationFooterProps).toEqual(
      expect.objectContaining({
        page: 1,
        perPage: 20,
        hasNext: false,
      })
    )
  })

  it('returns isViewingVersion false when viewingVersion is null', () => {
    const params = createDefaultParams()
    const { result } = renderHook(() => useBuilderVersionHistory(params), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.isViewingVersion).toBe(false)
  })

  it('returns isViewingVersion true when viewingVersion is set', () => {
    const params = createDefaultParams()
    params.viewingVersion = 2
    const { result } = renderHook(() => useBuilderVersionHistory(params), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.isViewingVersion).toBe(true)
  })

  it('returns viewed version date when viewing a version', () => {
    const params = createDefaultParams()
    params.viewingVersion = 2
    const { result } = renderHook(() => useBuilderVersionHistory(params), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.viewedVersionDate).toBe('2026-05-19T14:30:00.000Z')
  })

  it('returns viewed version description when viewing a version', () => {
    const params = createDefaultParams()
    params.viewingVersion = 2
    const { result } = renderHook(() => useBuilderVersionHistory(params), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.viewedVersionDescription).toBe('Bug fix')
  })

  it('returns viewed version publish name when viewing a version', () => {
    const params = createDefaultParams()
    params.viewingVersion = 2
    const { result } = renderHook(() => useBuilderVersionHistory(params), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.viewedVersionName).toBe('Release 1.0')
  })

  it('loads version definition into store when viewing a version', () => {
    const params = createDefaultParams()
    params.viewingVersion = 2
    renderHook(() => useBuilderVersionHistory(params), {
      wrapper: makeWrapper(queryClient),
    })

    expect(mockLoadWorkflowWithEdges).toHaveBeenCalled()
  })

  describe('handleExitVersionView', () => {
    it('dispatches EXIT_VERSION_VIEW and SET_VERSION_HISTORY_OPEN', () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderVersionHistory(params), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.handleExitVersionView()
      })

      expect(params.dispatch).toHaveBeenCalledWith({ type: 'EXIT_VERSION_VIEW' })
      expect(params.dispatch).toHaveBeenCalledWith({ type: 'SET_VERSION_HISTORY_OPEN', payload: false })
    })

    it('reloads current workflow definition into store', () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderVersionHistory(params), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.handleExitVersionView()
      })

      expect(mockLoadWorkflowWithEdges).toHaveBeenCalled()
    })

    it('handles exit when workflow has no version definition', () => {
      const params = createDefaultParams()
      params.workflow = { name: 'test' } as unknown as Parameters<typeof useBuilderVersionHistory>[0]['workflow']
      const { result } = renderHook(() => useBuilderVersionHistory(params), {
        wrapper: makeWrapper(queryClient),
      })

      mockLoadWorkflowWithEdges.mockClear()
      act(() => {
        result.current.handleExitVersionView()
      })

      expect(params.dispatch).toHaveBeenCalledWith({ type: 'EXIT_VERSION_VIEW' })
      expect(mockLoadWorkflowWithEdges).not.toHaveBeenCalled()
    })

    it('handles exit when workflow is undefined', () => {
      const params = createDefaultParams()
      params.workflow = undefined
      const { result } = renderHook(() => useBuilderVersionHistory(params), {
        wrapper: makeWrapper(queryClient),
      })

      mockLoadWorkflowWithEdges.mockClear()
      act(() => {
        result.current.handleExitVersionView()
      })

      expect(params.dispatch).toHaveBeenCalledWith({ type: 'EXIT_VERSION_VIEW' })
      expect(mockLoadWorkflowWithEdges).not.toHaveBeenCalled()
    })

    it('dispatches expandAll event when expandAllEvent is provided', () => {
      const expandAllEvent = new EventTarget()
      const dispatchSpy = vi.spyOn(expandAllEvent, 'dispatchEvent')
      const params = { ...createDefaultParams(), expandAllEvent }

      const { result } = renderHook(() => useBuilderVersionHistory(params), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.handleExitVersionView()
      })

      expect(dispatchSpy).toHaveBeenCalledWith(expect.objectContaining({ type: 'expandAll' }))
    })
  })

  describe('handleConfirmRestore', () => {
    it('does nothing when restore dialog has no item', () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderVersionHistory(params), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.handleConfirmRestore()
      })

      expect(mockRestoreMutate).not.toHaveBeenCalled()
    })

    it('does nothing when workflowId is null', () => {
      const params = createDefaultParams()
      params.workflowId = null
      const { result } = renderHook(() => useBuilderVersionHistory(params), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.restoreDialog.open({ version: 1, dateTime: '2026-05-19T14:30:00.000Z' })
      })

      act(() => {
        result.current.handleConfirmRestore()
      })

      expect(mockRestoreMutate).not.toHaveBeenCalled()
    })

    it('calls restore mutation when dialog has item and workflowId is set', () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderVersionHistory(params), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.restoreDialog.open({ version: 2, dateTime: '2026-05-19T14:30:00.000Z' })
      })

      act(() => {
        result.current.handleConfirmRestore()
      })

      expect(mockRestoreMutate).toHaveBeenCalledWith(
        { params: { path: { workflow_id: 'wf-1', version: 2 } } },
        expect.objectContaining({
          onSuccess: expect.any(Function) as unknown,
          onError: expect.any(Function) as unknown,
        })
      )
    })

    it('shows success alert and dispatches EXIT_VERSION_VIEW on restore success', () => {
      mockRestoreMutate.mockImplementation((_params: unknown, callbacks?: { onSuccess?: (data: unknown) => void }) => {
        callbacks?.onSuccess?.({ version: { workflow_definition: { name: 'restored' } } })
      })

      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderVersionHistory(params), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.restoreDialog.open({ version: 2, dateTime: '2026-05-19T14:30:00.000Z' })
      })

      act(() => {
        result.current.handleConfirmRestore()
      })

      expect(params.showSuccess).toHaveBeenCalledWith({
        title: 'Version restored',
        description: 'Restored from version 2',
      })
      expect(params.dispatch).toHaveBeenCalledWith({ type: 'EXIT_VERSION_VIEW' })
    })

    it('skips loading definition into store when restore response has no workflow_definition', () => {
      mockRestoreMutate.mockImplementation((_params: unknown, callbacks?: { onSuccess?: (data: unknown) => void }) => {
        callbacks?.onSuccess?.({ version: {} })
      })
      mockLoadWorkflowWithEdges.mockClear()

      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderVersionHistory(params), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.restoreDialog.open({ version: 2, dateTime: '2026-05-19T14:30:00.000Z' })
      })

      const callCountBefore = mockLoadWorkflowWithEdges.mock.calls.length
      act(() => {
        result.current.handleConfirmRestore()
      })

      expect(mockLoadWorkflowWithEdges.mock.calls.length).toBe(callCountBefore)
      expect(params.showSuccess).toHaveBeenCalled()
    })

    it('shows error alert on restore failure', () => {
      mockRestoreMutate.mockImplementation((_params: unknown, callbacks?: { onError?: () => void }) => {
        callbacks?.onError?.()
      })

      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderVersionHistory(params), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.restoreDialog.open({ version: 2, dateTime: '2026-05-19T14:30:00.000Z' })
      })

      act(() => {
        result.current.handleConfirmRestore()
      })

      expect(params.showError).toHaveBeenCalledWith({
        title: 'Failed to restore version',
        description: 'An unexpected error occurred',
      })
    })

    it('shows blocked step types and keeps the restore dialog open when permission is denied', () => {
      mockRestoreMutate.mockImplementation((_params: unknown, callbacks?: { onError?: (error: unknown) => void }) => {
        callbacks?.onError?.({
          cause: {
            code: 'NODE_KIND_WRITE_DENIED',
            blocked_step_types: [{ kind: 'script', label: 'Script', reason: 'explicit_deny' }],
          },
        })
      })
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderVersionHistory(params), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => result.current.restoreDialog.open({ version: 1, dateTime: '2026-05-19T14:30:00.000Z' }))
      act(() => result.current.handleConfirmRestore())

      expect(params.showError).toHaveBeenCalledWith({
        title: 'Failed to restore version',
        description: 'Step types not allowed: Script (write denied).',
      })
      expect(result.current.restoreDialog.isOpen).toBe(true)
      expect(params.showSuccess).not.toHaveBeenCalled()
    })
  })

  it('returns viewedVersionStatus from the viewed version query', () => {
    const params = createDefaultParams()
    params.viewingVersion = 2
    const { result } = renderHook(() => useBuilderVersionHistory(params), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.viewedVersionStatus).toBeDefined()
  })

  it('returns null viewedVersionStatus when not viewing a version', () => {
    const params = createDefaultParams()
    const { result } = renderHook(() => useBuilderVersionHistory(params), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.viewedVersionStatus).toBeNull()
  })

  it('exposes versionsQuery for external refetch', () => {
    const params = createDefaultParams()
    const { result } = renderHook(() => useBuilderVersionHistory(params), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.versionsQuery).toBeDefined()
    expect(result.current.versionsQuery.refetch).toBeDefined()
  })

  it('exposes publishVersion from useVersionHistory', () => {
    const params = createDefaultParams()
    const { result } = renderHook(() => useBuilderVersionHistory(params), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.publishVersion).toBeDefined()
    expect(typeof result.current.publishVersion).toBe('function')
  })

  it('does not dispatch expandAll when expandAllEvent is not provided in exit', () => {
    const params = createDefaultParams()
    delete (params as Record<string, unknown>).expandAllEvent
    const { result } = renderHook(() => useBuilderVersionHistory(params), {
      wrapper: makeWrapper(queryClient),
    })

    act(() => {
      result.current.handleExitVersionView()
    })

    expect(params.dispatch).toHaveBeenCalledWith({ type: 'EXIT_VERSION_VIEW' })
  })

  it('clears version URL param on handleExitVersionView', () => {
    const setSearchParams = vi.fn()
    const params = createDefaultParams()
    params.setSearchParams = setSearchParams
    params.searchParams = new URLSearchParams('version=2')
    const { result } = renderHook(() => useBuilderVersionHistory(params), {
      wrapper: makeWrapper(queryClient),
    })

    act(() => {
      result.current.handleExitVersionView()
    })

    expect(setSearchParams).toHaveBeenCalled()
    const calledParams = setSearchParams.mock.calls[0][0] as URLSearchParams
    expect(calledParams.has('version')).toBe(false)
  })

  it('exposes restoreMutation for loading state', () => {
    const params = createDefaultParams()
    const { result } = renderHook(() => useBuilderVersionHistory(params), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.restoreMutation).toBeDefined()
    expect(result.current.restoreMutation.isPending).toBe(false)
  })

  describe('restoreDialogTitle', () => {
    it('returns empty string when no dialog item', () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderVersionHistory(params), {
        wrapper: makeWrapper(queryClient),
      })

      expect(result.current.restoreDialogTitle).toBe('')
    })

    it('returns formatted title when dialog item is set', () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderVersionHistory(params), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.restoreDialog.open({ version: 1, dateTime: '2026-05-19T14:30:00.000Z' })
      })

      expect(result.current.restoreDialogTitle).toContain('Restore version from')
    })
  })
})

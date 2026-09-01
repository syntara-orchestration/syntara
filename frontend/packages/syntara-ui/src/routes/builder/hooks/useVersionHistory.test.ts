import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { workflowClient } from '../../../client'

import { isVersionStatus, useVersionHistory } from './useVersionHistory'

const mockMutate = vi.fn()
const mockRefetch = vi.fn()
const mockShowSuccess = vi.fn()
const mockShowError = vi.fn()

let mockNextCursor: string | null = 'cursor-page-2'
let mockTotal = 45
let mockVersions: Array<{
  version: number
  status: string
  name?: string | null
  workflow_definition: { name: string }
}> = [
  { version: 3, status: 'draft', workflow_definition: { name: 'v3' } },
  { version: 2, status: 'published', workflow_definition: { name: 'v2' } },
  { version: 1, status: 'previously_published', workflow_definition: { name: 'v1' } },
]

vi.mock('../../../providers/alerts', () => ({
  useAlerts: () => ({
    showSuccess: mockShowSuccess,
    showError: mockShowError,
  }),
}))

vi.mock('../../../utils/apiErrors', () => ({
  getErrorMessage: (e: unknown) => (e instanceof Error ? e.message : 'Unknown error'),
}))

const mockDownloadVersionExport = vi.fn().mockResolvedValue(undefined)
vi.mock('../../../utils/downloadWorkflowExport', () => ({
  downloadVersionExport: (workflowId: string, version: number) =>
    mockDownloadVersionExport(workflowId, version) as Promise<void>,
}))

vi.mock('../../../client', () => ({
  workflowClient: {
    useQuery: vi.fn((_method: string, _path: string, _params: unknown, opts: { enabled: boolean }) => ({
      data: opts.enabled ? { resources: mockVersions, next: mockNextCursor, prev: null, total: mockTotal } : undefined,
      refetch: mockRefetch,
    })),
    useMutation: vi.fn(() => ({
      mutate: mockMutate,
      isPending: false,
    })),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

function makeWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('useVersionHistory', () => {
  describe('isVersionStatus', () => {
    it('returns true for valid status strings', () => {
      expect(isVersionStatus('draft')).toBe(true)
      expect(isVersionStatus('published')).toBe(true)
      expect(isVersionStatus('previously_published')).toBe(true)
    })

    it('returns false for invalid status strings', () => {
      expect(isVersionStatus('unknown')).toBe(false)
      expect(isVersionStatus('')).toBe(false)
    })
  })

  let queryClient: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    mockNextCursor = 'cursor-page-2'
    mockTotal = 45
    mockRefetch.mockResolvedValue({ data: { resources: mockVersions } })
    mockDownloadVersionExport.mockResolvedValue(undefined)
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    mockVersions = [
      { version: 3, status: 'draft', workflow_definition: { name: 'v3' } },
      { version: 2, status: 'published', workflow_definition: { name: 'v2' } },
      { version: 1, status: 'previously_published', workflow_definition: { name: 'v1' } },
    ]
  })

  it('requests versions with cursor pagination params', () => {
    renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
      wrapper: makeWrapper(queryClient),
    })

    const useQueryMock = vi.mocked(workflowClient.useQuery)
    expect(useQueryMock).toHaveBeenCalled()
    const [method, path, request, options] = useQueryMock.mock.calls[0] as unknown as [
      string,
      string,
      { params: { path: { workflow_id: string }; query: { limit: number; include_total: boolean } } },
      { enabled: boolean },
    ]
    expect(method).toBe('get')
    expect(path).toBe('/workflows/{workflow_id}/versions')
    expect(request.params.path.workflow_id).toBe('wf-1')
    expect(request.params.query.limit).toBe(20)
    expect(request.params.query.include_total).toBe(true)
    expect(options.enabled).toBe(true)
  })

  it('exposes paginationFooterProps from the versions query', () => {
    const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.paginationFooterProps).toEqual(
      expect.objectContaining({
        page: 1,
        perPage: 20,
        total: 45,
        hasNext: true,
      })
    )
  })

  it('includes cursor in versions query after navigating to the next page', () => {
    const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
      wrapper: makeWrapper(queryClient),
    })

    act(() => {
      result.current.paginationFooterProps.onNext()
    })

    const useQueryMock = vi.mocked(workflowClient.useQuery)
    const lastCall = useQueryMock.mock.calls.at(-1) as unknown as [
      string,
      string,
      { params: { query: { cursor?: string; limit: number } } },
    ]
    expect(lastCall[2].params.query.cursor).toBe('cursor-page-2')
    expect(lastCall[2].params.query.limit).toBe(20)
  })

  it('resets pagination when the status filter changes', () => {
    const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
      wrapper: makeWrapper(queryClient),
    })

    act(() => {
      result.current.paginationFooterProps.onNext()
    })
    expect(result.current.paginationFooterProps.page).toBe(2)

    act(() => {
      result.current.setStatusFilter(['published'])
    })

    expect(result.current.paginationFooterProps.page).toBe(1)
    const useQueryMock = vi.mocked(workflowClient.useQuery)
    const lastCall = useQueryMock.mock.calls.at(-1) as unknown as [
      string,
      string,
      { params: { query: { cursor?: string } } },
    ]
    expect(lastCall[2].params.query.cursor).toBeUndefined()
  })

  it('returns all versions when no status filter is set', () => {
    const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.filteredVersions).toHaveLength(3)
  })

  it('returns publishedVersionName from the published version name when present', () => {
    mockVersions = [
      { version: 2, status: 'published', name: 'Release 1.0', workflow_definition: { name: 'v2' } },
      { version: 1, status: 'previously_published', name: null, workflow_definition: { name: 'v1' } },
    ]

    const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.publishedVersionName).toBe('Release 1.0')
  })

  it('falls back to Version N when published version has no name', () => {
    mockVersions = [
      { version: 3, status: 'draft', name: null, workflow_definition: { name: 'v3' } },
      { version: 2, status: 'published', name: null, workflow_definition: { name: 'v2' } },
    ]

    const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.publishedVersionName).toBe('Version 2')
  })

  it('returns null publishedVersionName when no published version exists', () => {
    mockVersions = [{ version: 1, status: 'draft', name: null, workflow_definition: { name: 'v1' } }]

    const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.publishedVersionName).toBeNull()
  })

  it('updates perPage through paginationFooterProps', () => {
    const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
      wrapper: makeWrapper(queryClient),
    })

    act(() => {
      result.current.paginationFooterProps.onPerPageChange(10)
    })

    expect(result.current.paginationFooterProps.perPage).toBe(10)
    expect(result.current.paginationFooterProps.page).toBe(1)
  })

  it('filters versions by status when filter is set', () => {
    const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
      wrapper: makeWrapper(queryClient),
    })

    act(() => {
      result.current.setStatusFilter(['published'])
    })

    expect(result.current.filteredVersions).toHaveLength(1)
    expect(result.current.filteredVersions[0].version).toBe(2)
  })

  it('returns empty array when no versions match the filter', () => {
    mockVersions = [{ version: 1, status: 'draft', workflow_definition: { name: 'v1' } }]

    const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
      wrapper: makeWrapper(queryClient),
    })

    act(() => {
      result.current.setStatusFilter(['published'])
    })

    expect(result.current.filteredVersions).toHaveLength(0)
  })

  it('returns empty array when workflowId is null', () => {
    const { result } = renderHook(() => useVersionHistory({ workflowId: null, isNew: false }), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.filteredVersions).toHaveLength(0)
  })

  it('returns empty array when isNew is true', () => {
    const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: true }), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.filteredVersions).toHaveLength(0)
  })

  describe('exportVersion', () => {
    it('calls downloadVersionExport with correct params', () => {
      const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.exportVersion(2)
      })

      expect(mockDownloadVersionExport).toHaveBeenCalledWith('wf-1', 2)
    })

    it('shows an error alert when export fails', async () => {
      mockDownloadVersionExport.mockRejectedValueOnce(new Error('disk full'))

      const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.exportVersion(2)
      })

      await vi.waitFor(() => {
        expect(mockShowError).toHaveBeenCalledWith({
          title: 'Export failed',
          description: 'disk full',
        })
      })
    })

    it('does nothing when workflowId is not set', () => {
      const { result } = renderHook(() => useVersionHistory({ workflowId: null, isNew: false }), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.exportVersion(2)
      })

      expect(mockDownloadVersionExport).not.toHaveBeenCalled()
    })
  })

  describe('openInNewWindow', () => {
    it('opens a new window with the version URL', () => {
      const mockOpen = vi.spyOn(window, 'open').mockImplementation(() => null)

      const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.openInNewWindow(2)
      })

      expect(mockOpen).toHaveBeenCalledWith('/workflow-builder/wf-1?version=2', '_blank', 'noopener,noreferrer')
      mockOpen.mockRestore()
    })

    it('does nothing when workflowId is null', () => {
      const mockOpen = vi.spyOn(window, 'open').mockImplementation(() => null)

      const { result } = renderHook(() => useVersionHistory({ workflowId: null, isNew: false }), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.openInNewWindow(2)
      })

      expect(mockOpen).not.toHaveBeenCalled()
      mockOpen.mockRestore()
    })
  })

  it('returns empty filteredVersions when allVersions is undefined', () => {
    const { result } = renderHook(() => useVersionHistory({ workflowId: null, isNew: false }), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.filteredVersions).toEqual([])
  })

  it('filters versions with multiple status values', () => {
    const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
      wrapper: makeWrapper(queryClient),
    })

    act(() => {
      result.current.setStatusFilter(['draft', 'published'])
    })

    expect(result.current.filteredVersions).toHaveLength(2)
  })

  it('exposes restoreMutation', () => {
    const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.restoreMutation).toBeDefined()
    expect(result.current.restoreMutation.isPending).toBe(false)
  })

  it('exposes versionsQuery', () => {
    const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.versionsQuery).toBeDefined()
    expect(result.current.versionsQuery.refetch).toBeDefined()
  })

  describe('publishVersion', () => {
    it('calls publish mutation with correct params', () => {
      const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.publishVersion(2)
      })

      expect(mockMutate).toHaveBeenCalledWith(
        {
          params: { path: { workflow_id: 'wf-1', version: 2 } },
          body: { name: null, change_description: null },
        },
        expect.objectContaining({
          onSuccess: expect.any(Function) as unknown,
          onError: expect.any(Function) as unknown,
        })
      )
    })

    it('passes publishName and changeDescription when provided', () => {
      const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.publishVersion(2, 'Release 1.0', 'First public release')
      })

      expect(mockMutate).toHaveBeenCalledWith(
        {
          params: { path: { workflow_id: 'wf-1', version: 2 } },
          body: { name: 'Release 1.0', change_description: 'First public release' },
        },
        expect.objectContaining({
          onSuccess: expect.any(Function) as unknown,
          onError: expect.any(Function) as unknown,
        })
      )
    })

    it('refetches versions and invalidates queries on publish success', () => {
      mockMutate.mockImplementation((_params: unknown, callbacks?: { onSuccess?: () => void }) => {
        callbacks?.onSuccess?.()
      })

      const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.publishVersion(2)
      })

      expect(mockRefetch).toHaveBeenCalled()
      expect(mockShowSuccess).toHaveBeenCalledWith({ title: 'Version published' })
    })

    it('calls onVersionUpdated when publish response includes current_version', () => {
      const onVersionUpdated = vi.fn()
      mockMutate.mockImplementation(
        (_params: unknown, callbacks?: { onSuccess?: (data: { current_version: number }) => void }) => {
          callbacks?.onSuccess?.({ current_version: 9 })
        }
      )

      const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false, onVersionUpdated }), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.publishVersion(2)
      })

      expect(onVersionUpdated).toHaveBeenCalledWith(9)
    })

    it('does not call onVersionUpdated when publish response omits current_version', () => {
      const onVersionUpdated = vi.fn()
      mockMutate.mockImplementation((_params: unknown, callbacks?: { onSuccess?: (data: object) => void }) => {
        callbacks?.onSuccess?.({})
      })

      const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false, onVersionUpdated }), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.publishVersion(2)
      })

      expect(onVersionUpdated).not.toHaveBeenCalled()
    })

    it('does not call mutation when workflowId is null', () => {
      const { result } = renderHook(() => useVersionHistory({ workflowId: null, isNew: false }), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.publishVersion(2)
      })

      expect(mockMutate).not.toHaveBeenCalled()
    })

    it('shows success alert on publish success', () => {
      mockMutate.mockImplementation((_params: unknown, callbacks?: { onSuccess?: () => void }) => {
        callbacks?.onSuccess?.()
      })

      const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.publishVersion(2)
      })

      expect(mockShowSuccess).toHaveBeenCalledWith({ title: 'Version published' })
    })

    it('shows error alert on publish failure', () => {
      const mockError = new Error('Publish failed')
      mockMutate.mockImplementation((_params: unknown, callbacks?: { onError?: (error: unknown) => void }) => {
        callbacks?.onError?.(mockError)
      })

      const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.publishVersion(2)
      })

      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Failed to publish version',
        description: 'Publish failed',
      })
    })
  })

  describe('updateVersionMetadata', () => {
    it('calls mutate with correct params', () => {
      const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.updateVersionMetadata(2, 'new name', 'new desc')
      })

      expect(mockMutate).toHaveBeenCalled()
      const [args] = mockMutate.mock.calls[0] as [Record<string, unknown>]
      expect(args).toEqual({
        params: { path: { workflow_id: 'wf-1', version: 2 } },
        body: { name: 'new name', change_description: 'new desc' },
      })
    })

    it('shows success toast on successful update', () => {
      mockMutate.mockImplementation((_args: unknown, callbacks: { onSuccess?: () => void }) => {
        callbacks?.onSuccess?.()
      })

      const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.updateVersionMetadata(2, 'name', 'desc')
      })

      expect(mockShowSuccess).toHaveBeenCalledWith({ title: 'Version updated' })
    })

    it('shows error toast on failure', () => {
      const mockError = new Error('Update failed')
      mockMutate.mockImplementation((_args: unknown, callbacks: { onError?: (e: Error) => void }) => {
        callbacks?.onError?.(mockError)
      })

      const { result } = renderHook(() => useVersionHistory({ workflowId: 'wf-1', isNew: false }), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.updateVersionMetadata(2, 'name', 'desc')
      })

      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Failed to update version',
        description: 'Update failed',
      })
    })

    it('does not call mutate when workflowId is null', () => {
      const { result } = renderHook(() => useVersionHistory({ workflowId: null, isNew: false }), {
        wrapper: makeWrapper(queryClient),
      })

      act(() => {
        result.current.updateVersionMetadata(2, 'name', 'desc')
      })

      expect(mockMutate).not.toHaveBeenCalled()
    })
  })
})

import type { IntegrationsAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { integrationsClient } from '../../../client'
import { AlertProvider } from '../../../providers/alerts/AlertProvider'

import { chunkedBulkUpdate, useModelSave, type SaveParams } from './useModelSave'

vi.mock('../../../client', () => ({
  integrationsClient: {
    useMutation: vi.fn(),
  },
}))

type LLMModelRead = IntegrationsAPI.components['schemas']['LLMModelRead']

const mockBulkUpdateAsync = vi.fn().mockResolvedValue({})
const mockUpdateModelAsync = vi.fn().mockResolvedValue({})

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

function makeModel(overrides: Partial<LLMModelRead> & { id: string }): LLMModelRead {
  return {
    integration_id: 'int-1',
    model_id: overrides.id,
    name: `model-${overrides.id}`,
    description: null,
    enabled: false,
    is_default: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

const models: LLMModelRead[] = [
  makeModel({ id: 'm1', enabled: true, is_default: true }),
  makeModel({ id: 'm2', enabled: true }),
  makeModel({ id: 'm3', enabled: false }),
]

function makeSaveParams(overrides: Partial<SaveParams> = {}): SaveParams {
  return {
    models,
    enabledModelIds: new Set(['m1', 'm2']),
    defaultModelId: 'm1',
    serverDefaultId: 'm1',
    isDefaultDirty: false,
    ...overrides,
  }
}

describe('chunkedBulkUpdate', () => {
  const mockFn = vi.fn()

  beforeEach(() => {
    mockFn.mockReset()
    mockFn.mockResolvedValue({ updated_count: 0, skipped_count: 0 })
  })

  it('sends all IDs in a single call when under batch size', async () => {
    const ids = ['a', 'b', 'c']
    mockFn.mockResolvedValue({ updated_count: 3, skipped_count: 0 })

    const result = await chunkedBulkUpdate(mockFn, 'int-1', ids, true)

    expect(mockFn).toHaveBeenCalledTimes(1)
    expect(mockFn).toHaveBeenCalledWith({
      params: { path: { integration_id: 'int-1' } },
      body: { model_ids: ['a', 'b', 'c'], enabled: true },
    })
    expect(result).toEqual({ updated_count: 3, skipped_count: 0 })
  })

  it('splits into batches of 1000 and aggregates results', async () => {
    const ids = Array.from({ length: 2500 }, (_, i) => `id-${i}`)
    mockFn
      .mockResolvedValueOnce({ updated_count: 1000, skipped_count: 0 })
      .mockResolvedValueOnce({ updated_count: 1000, skipped_count: 0 })
      .mockResolvedValueOnce({ updated_count: 500, skipped_count: 0 })

    const result = await chunkedBulkUpdate(mockFn, 'int-1', ids, false)

    expect(mockFn).toHaveBeenCalledTimes(3)
    expect(mockFn).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({ body: { model_ids: ids.slice(0, 1000), enabled: false } })
    )
    expect(mockFn).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ body: { model_ids: ids.slice(1000, 2000), enabled: false } })
    )
    expect(mockFn).toHaveBeenNthCalledWith(
      3,
      expect.objectContaining({ body: { model_ids: ids.slice(2000, 2500), enabled: false } })
    )
    expect(result).toEqual({ updated_count: 2500, skipped_count: 0 })
  })

  it('aggregates skipped counts across batches', async () => {
    const ids = Array.from({ length: 1500 }, (_, i) => `id-${i}`)
    mockFn
      .mockResolvedValueOnce({ updated_count: 990, skipped_count: 10 })
      .mockResolvedValueOnce({ updated_count: 495, skipped_count: 5 })

    const result = await chunkedBulkUpdate(mockFn, 'int-1', ids, true)

    expect(result).toEqual({ updated_count: 1485, skipped_count: 15 })
  })

  it('handles exactly 1000 IDs without splitting', async () => {
    const ids = Array.from({ length: 1000 }, (_, i) => `id-${i}`)
    mockFn.mockResolvedValue({ updated_count: 1000, skipped_count: 0 })

    await chunkedBulkUpdate(mockFn, 'int-1', ids, true)

    expect(mockFn).toHaveBeenCalledTimes(1)
    expect(mockFn).toHaveBeenCalledWith(expect.objectContaining({ body: { model_ids: ids, enabled: true } }))
  })

  it('handles empty array without calling the API', async () => {
    const result = await chunkedBulkUpdate(mockFn, 'int-1', [], true)

    expect(mockFn).not.toHaveBeenCalled()
    expect(result).toEqual({ updated_count: 0, skipped_count: 0 })
  })

  it('propagates errors from the bulk update function', async () => {
    const ids = Array.from({ length: 1500 }, (_, i) => `id-${i}`)
    mockFn.mockResolvedValueOnce({ updated_count: 1000, skipped_count: 0 }).mockRejectedValueOnce(new Error('fail'))

    await expect(chunkedBulkUpdate(mockFn, 'int-1', ids, true)).rejects.toThrow('fail')
    expect(mockFn).toHaveBeenCalledTimes(2)
  })
})

describe('useModelSave', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    mockBulkUpdateAsync.mockResolvedValue({})
    mockUpdateModelAsync.mockResolvedValue({})

    vi.mocked(integrationsClient.useMutation).mockImplementation((_method: string, path: string) => {
      if (path.includes('bulk_update')) {
        return {
          mutateAsync: mockBulkUpdateAsync,
          mutate: vi.fn(),
          isPending: false,
          isIdle: true,
          isSuccess: false,
          isError: false,
          error: null,
          data: null,
          reset: vi.fn(),
          failureCount: 0,
          failureReason: null,
          context: undefined,
          submittedAt: 0,
          variables: undefined,
          status: 'idle',
          isPaused: false,
        } as never
      }
      return {
        mutateAsync: mockUpdateModelAsync,
        mutate: vi.fn(),
        isPending: false,
        isIdle: true,
        isSuccess: false,
        isError: false,
        error: null,
        data: null,
        reset: vi.fn(),
        failureCount: 0,
        failureReason: null,
        context: undefined,
        submittedAt: 0,
        variables: undefined,
        status: 'idle',
        isPaused: false,
      } as never
    })
  })

  it('calls bulkUpdateModels with correct enable/disable sets', async () => {
    const { result } = renderHook(() => useModelSave('int-1'), { wrapper })

    const params = makeSaveParams({
      enabledModelIds: new Set(['m1', 'm3']),
    })

    await act(async () => {
      await result.current.save(params)
    })

    // Enable call: m1 and m3 are in the enabled set
    expect(mockBulkUpdateAsync).toHaveBeenCalledWith({
      params: { path: { integration_id: 'int-1' } },
      body: { model_ids: ['m1', 'm3'], enabled: true },
    })

    // Disable call: m2 is not in the enabled set
    expect(mockBulkUpdateAsync).toHaveBeenCalledWith({
      params: { path: { integration_id: 'int-1' } },
      body: { model_ids: ['m2'], enabled: false },
    })
  })

  it('calls updateModel when isDefaultDirty with a new default', async () => {
    const { result } = renderHook(() => useModelSave('int-1'), { wrapper })

    const params = makeSaveParams({
      isDefaultDirty: true,
      defaultModelId: 'm2',
      serverDefaultId: 'm1',
    })

    await act(async () => {
      await result.current.save(params)
    })

    expect(mockUpdateModelAsync).toHaveBeenCalledWith({
      params: { path: { integration_id: 'int-1', model_id: 'm2' } },
      body: { is_default: true },
    })
  })

  it('clears the default when isDefaultDirty with null defaultModelId', async () => {
    const { result } = renderHook(() => useModelSave('int-1'), { wrapper })

    const params = makeSaveParams({
      isDefaultDirty: true,
      defaultModelId: null,
      serverDefaultId: 'm1',
    })

    await act(async () => {
      await result.current.save(params)
    })

    expect(mockUpdateModelAsync).toHaveBeenCalledWith({
      params: { path: { integration_id: 'int-1', model_id: 'm1' } },
      body: { is_default: false },
    })
  })

  it('does not call updateModel when isDefaultDirty is false', async () => {
    const { result } = renderHook(() => useModelSave('int-1'), { wrapper })

    const params = makeSaveParams({ isDefaultDirty: false })

    await act(async () => {
      await result.current.save(params)
    })

    expect(mockUpdateModelAsync).not.toHaveBeenCalled()
  })

  it('skips bulkUpdateModels when all models match their enable state', async () => {
    const { result } = renderHook(() => useModelSave('int-1'), { wrapper })

    // All models enabled
    const params = makeSaveParams({
      enabledModelIds: new Set(['m1', 'm2', 'm3']),
    })

    await act(async () => {
      await result.current.save(params)
    })

    // Only one bulk call for enabling all; no disable call since toDisable is empty
    expect(mockBulkUpdateAsync).toHaveBeenCalledTimes(1)
    expect(mockBulkUpdateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        body: { model_ids: ['m1', 'm2', 'm3'], enabled: true },
      })
    )
  })

  it('returns true on success', async () => {
    const { result } = renderHook(() => useModelSave('int-1'), { wrapper })

    let saveResult: boolean | undefined
    await act(async () => {
      saveResult = await result.current.save(makeSaveParams())
    })

    expect(saveResult).toBe(true)
  })

  it('returns false on failure', async () => {
    mockBulkUpdateAsync.mockRejectedValueOnce(new Error('Network error'))

    const { result } = renderHook(() => useModelSave('int-1'), { wrapper })

    let saveResult: boolean | undefined
    await act(async () => {
      saveResult = await result.current.save(makeSaveParams())
    })

    expect(saveResult).toBe(false)
  })

  it('sets isSaving during the save operation', async () => {
    // Use a single-model set so only one bulkUpdateModels call is made
    const singleModel = [makeModel({ id: 'm1', enabled: true })]
    let resolveBulk: () => void = () => {}
    mockBulkUpdateAsync.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveBulk = resolve
        })
    )

    const { result } = renderHook(() => useModelSave('int-1'), { wrapper })

    expect(result.current.isSaving).toBe(false)

    let savePromise: Promise<boolean> | undefined
    act(() => {
      savePromise = result.current.save({
        models: singleModel,
        enabledModelIds: new Set(['m1']),
        defaultModelId: null,
        serverDefaultId: null,
        isDefaultDirty: false,
      })
    })

    expect(result.current.isSaving).toBe(true)

    await act(async () => {
      resolveBulk()
      await savePromise
    })

    expect(result.current.isSaving).toBe(false)
  })

  it('invalidates queries on success', async () => {
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue()

    const { result } = renderHook(() => useModelSave('int-1'), { wrapper })

    await act(async () => {
      await result.current.save(makeSaveParams())
    })

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['all-integration-models', 'int-1'],
    })
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['get', '/integrations/{integration_id}'],
    })

    invalidateSpy.mockRestore()
  })

  it('invalidates queries on partial failure (I17)', async () => {
    // Bulk update succeeds, but updateModel fails
    mockUpdateModelAsync.mockRejectedValueOnce(new Error('Default update failed'))
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue()

    const { result } = renderHook(() => useModelSave('int-1'), { wrapper })

    const params = makeSaveParams({
      isDefaultDirty: true,
      defaultModelId: 'm2',
    })

    await act(async () => {
      await result.current.save(params)
    })

    // Queries should still be invalidated even on failure
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['all-integration-models', 'int-1'],
    })
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['get', '/integrations/{integration_id}'],
    })

    invalidateSpy.mockRestore()
  })
})

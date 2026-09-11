import { renderHook, act } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useIntegrationModelsState } from './useIntegrationModelsState'

const mockModels = [
  { id: 'm1', name: 'Model 1', enabled: true, is_default: true },
  { id: 'm2', name: 'Model 2', enabled: false, is_default: false },
]

const mockRegisterDirtyCheck = vi.fn(() => vi.fn())

vi.mock('../../../app/useUnsavedChanges', () => ({
  useUnsavedChanges: () => ({ registerDirtyCheck: mockRegisterDirtyCheck }),
}))

const mockRefetch = vi.fn()

vi.mock('./useAllIntegrationModels', () => ({
  useAllIntegrationModels: vi.fn(() => ({
    models: mockModels,
    isLoading: false,
    error: null,
    refetch: mockRefetch,
  })),
}))

const mockHandleSelectItem = vi.fn()
const mockResetToServer = vi.fn()

vi.mock('./useItemSelection', () => ({
  useItemSelection: vi.fn(() => ({
    enabledIds: new Set(['m1']),
    enabledCount: 1,
    allSelected: false,
    isDirty: false,
    handleSelectAll: vi.fn(),
    handleSelectItem: mockHandleSelectItem,
    resetToServer: mockResetToServer,
  })),
}))

const mockHandleSetDefault = vi.fn()
const mockHandleRemoveDefault = vi.fn()
const mockHandleSelectWithDefaultClear = vi.fn()
const mockResetDefault = vi.fn()

vi.mock('./useModelDefaultTracking', () => ({
  useModelDefaultTracking: vi.fn(() => ({
    defaultModelId: 'm1',
    serverDefaultId: 'm1',
    isDefaultDirty: false,
    handleSetDefault: mockHandleSetDefault,
    handleRemoveDefault: mockHandleRemoveDefault,
    handleSelectWithDefaultClear: mockHandleSelectWithDefaultClear,
    resetDefault: mockResetDefault,
  })),
}))

const mockSave = vi.fn(() => Promise.resolve(true))

vi.mock('./useModelSave', () => ({
  useModelSave: vi.fn(() => ({
    save: mockSave,
    isSaving: false,
  })),
}))

vi.mock('../../../utils/detachPromise', () => ({
  detachPromise: (p: Promise<unknown>) => p,
}))

describe('useIntegrationModelsState', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns composed state from sub-hooks', () => {
    const { result } = renderHook(() => useIntegrationModelsState('int-1', true))

    expect(result.current.models).toBe(mockModels)
    expect(result.current.isLoading).toBe(false)
    expect(result.current.error).toBeNull()
    expect(result.current.enabledModelIds).toEqual(new Set(['m1']))
    expect(result.current.enabledCount).toBe(1)
    expect(result.current.allSelected).toBe(false)
    expect(result.current.isDirty).toBe(false)
    expect(result.current.isSaving).toBe(false)
    expect(result.current.defaultModelId).toBe('m1')
  })

  it('exposes action handlers from sub-hooks', () => {
    const { result } = renderHook(() => useIntegrationModelsState('int-1', true))

    expect(result.current.handleSetDefault).toBe(mockHandleSetDefault)
    expect(result.current.handleRemoveDefault).toBe(mockHandleRemoveDefault)
    expect(result.current.handleSelectWithDefaultClear).toBe(mockHandleSelectWithDefaultClear)
    expect(result.current.resetSelectionToServer).toBe(mockResetToServer)
    expect(result.current.resetDefault).toBe(mockResetDefault)
  })

  it('registers a dirty check on mount', () => {
    renderHook(() => useIntegrationModelsState('int-1', true))

    expect(mockRegisterDirtyCheck).toHaveBeenCalledTimes(1)
    expect(mockRegisterDirtyCheck).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Save model changes?',
        saveLabel: 'Save models',
      })
    )
  })

  it('handleSave triggers the save function', () => {
    const { result } = renderHook(() => useIntegrationModelsState('int-1', true))

    act(() => {
      result.current.handleSave()
    })

    expect(mockSave).toHaveBeenCalledTimes(1)
  })

  it('dirty check exitWithoutSaving resets selection and default', () => {
    renderHook(() => useIntegrationModelsState('int-1', true))

    const calls = mockRegisterDirtyCheck.mock.calls as unknown as Array<[{ exitWithoutSaving: () => void }]>
    expect(calls).toHaveLength(1)
    calls[0][0].exitWithoutSaving()

    expect(mockResetToServer).toHaveBeenCalledTimes(1)
    expect(mockResetDefault).toHaveBeenCalledTimes(1)
  })
})

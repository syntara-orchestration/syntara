import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useModelDefaultTracking } from './useModelDefaultTracking'

type Model = {
  id: string
  integration_id: string
  model_id: string
  name: string
  enabled?: boolean
  is_default?: boolean
}

function makeModel(overrides: Partial<Model> & { id: string }): Model {
  return {
    integration_id: 'int-1',
    model_id: overrides.id,
    name: `Model ${overrides.id}`,
    enabled: true,
    is_default: false,
    ...overrides,
  }
}

const models: Model[] = [
  makeModel({ id: 'a', is_default: true }),
  makeModel({ id: 'b' }),
  makeModel({ id: 'c', enabled: false }),
]

const enabledIds = new Set(['a', 'b'])

describe('useModelDefaultTracking', () => {
  it('initializes defaultModelId from the server default', () => {
    const onSelect = vi.fn()
    const { result } = renderHook(() => useModelDefaultTracking(models, enabledIds, onSelect))

    expect(result.current.defaultModelId).toBe('a')
    expect(result.current.serverDefaultId).toBe('a')
  })

  it('starts with isDefaultDirty false', () => {
    const onSelect = vi.fn()
    const { result } = renderHook(() => useModelDefaultTracking(models, enabledIds, onSelect))

    expect(result.current.isDefaultDirty).toBe(false)
  })

  it('returns null defaultModelId when no model has is_default', () => {
    const noDefault = models.map((m) => ({ ...m, is_default: false }))
    const onSelect = vi.fn()
    const { result } = renderHook(() => useModelDefaultTracking(noDefault, enabledIds, onSelect))

    expect(result.current.defaultModelId).toBeNull()
    expect(result.current.serverDefaultId).toBeNull()
  })

  it('handleSetDefault sets a new default', () => {
    const onSelect = vi.fn()
    const { result } = renderHook(() => useModelDefaultTracking(models, enabledIds, onSelect))

    act(() => {
      result.current.handleSetDefault('b')
    })

    expect(result.current.defaultModelId).toBe('b')
    expect(result.current.isDefaultDirty).toBe(true)
  })

  it('handleSetDefault is a no-op when model is not in enabledModelIds (I13 guard)', () => {
    const onSelect = vi.fn()
    const { result } = renderHook(() => useModelDefaultTracking(models, enabledIds, onSelect))

    act(() => {
      result.current.handleSetDefault('c')
    })

    expect(result.current.defaultModelId).toBe('a')
    expect(result.current.isDefaultDirty).toBe(false)
  })

  it('handleRemoveDefault clears the default', () => {
    const onSelect = vi.fn()
    const { result } = renderHook(() => useModelDefaultTracking(models, enabledIds, onSelect))

    act(() => {
      result.current.handleRemoveDefault()
    })

    expect(result.current.defaultModelId).toBeNull()
    expect(result.current.isDefaultDirty).toBe(true)
  })

  it('handleSelectWithDefaultClear calls onSelectModel and clears default when disabling the default model', () => {
    const onSelect = vi.fn()
    const { result } = renderHook(() => useModelDefaultTracking(models, enabledIds, onSelect))

    act(() => {
      result.current.handleSelectWithDefaultClear('a', false)
    })

    expect(onSelect).toHaveBeenCalledWith('a', false)
    expect(result.current.defaultModelId).toBeNull()
    expect(result.current.isDefaultDirty).toBe(true)
  })

  it('handleSelectWithDefaultClear calls onSelectModel without clearing default for non-default model', () => {
    const onSelect = vi.fn()
    const { result } = renderHook(() => useModelDefaultTracking(models, enabledIds, onSelect))

    act(() => {
      result.current.handleSelectWithDefaultClear('b', false)
    })

    expect(onSelect).toHaveBeenCalledWith('b', false)
    expect(result.current.defaultModelId).toBe('a')
    expect(result.current.isDefaultDirty).toBe(false)
  })

  it('handleSelectWithDefaultClear does not clear default when enabling a model', () => {
    const onSelect = vi.fn()
    const { result } = renderHook(() => useModelDefaultTracking(models, enabledIds, onSelect))

    act(() => {
      result.current.handleSelectWithDefaultClear('a', true)
    })

    expect(onSelect).toHaveBeenCalledWith('a', true)
    expect(result.current.defaultModelId).toBe('a')
    expect(result.current.isDefaultDirty).toBe(false)
  })

  it('resetDefault syncs back to server state', () => {
    const onSelect = vi.fn()
    const { result } = renderHook(() => useModelDefaultTracking(models, enabledIds, onSelect))

    act(() => {
      result.current.handleSetDefault('b')
    })
    expect(result.current.defaultModelId).toBe('b')
    expect(result.current.isDefaultDirty).toBe(true)

    act(() => {
      result.current.resetDefault()
    })

    expect(result.current.defaultModelId).toBe('a')
    expect(result.current.isDefaultDirty).toBe(false)
  })

  it('syncs to new server state when models change (setState-during-render)', () => {
    const onSelect = vi.fn()
    const { result, rerender } = renderHook(
      ({ m, ids }: { m: Model[]; ids: Set<string> }) => useModelDefaultTracking(m, ids, onSelect),
      { initialProps: { m: models, ids: enabledIds } }
    )

    act(() => {
      result.current.handleSetDefault('b')
    })
    expect(result.current.defaultModelId).toBe('b')
    expect(result.current.isDefaultDirty).toBe(true)

    // Server now reflects 'b' as default
    const updatedModels = models.map((m) => (m.id === 'b' ? { ...m, is_default: true } : { ...m, is_default: false }))
    rerender({ m: updatedModels, ids: enabledIds })

    expect(result.current.defaultModelId).toBe('b')
    expect(result.current.serverDefaultId).toBe('b')
    expect(result.current.isDefaultDirty).toBe(false)
  })
})

import { renderHook, act } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useItemSelection } from './useItemSelection'

type TestItem = { id: string; enabled?: boolean }

const items: TestItem[] = [
  { id: '1', enabled: true },
  { id: '2', enabled: true },
  { id: '3', enabled: false },
  { id: '4', enabled: false },
]

describe('useItemSelection', () => {
  it('initializes enabledIds from server state', () => {
    const { result } = renderHook(() => useItemSelection(items, items))

    expect(result.current.enabledIds.has('1')).toBe(true)
    expect(result.current.enabledIds.has('2')).toBe(true)
    expect(result.current.enabledIds.has('3')).toBe(false)
  })

  it('computes enabledCount correctly', () => {
    const { result } = renderHook(() => useItemSelection(items, items))

    expect(result.current.enabledCount).toBe(2)
  })

  it('reports allSelected as false when not all filtered items are enabled', () => {
    const { result } = renderHook(() => useItemSelection(items, items))

    expect(result.current.allSelected).toBe(false)
  })

  it('reports allSelected as true when all filtered items are enabled', () => {
    const enabledOnly = items.filter((i) => i.enabled)
    const { result } = renderHook(() => useItemSelection(items, enabledOnly))

    expect(result.current.allSelected).toBe(true)
  })

  it('starts with isDirty false', () => {
    const { result } = renderHook(() => useItemSelection(items, items))

    expect(result.current.isDirty).toBe(false)
  })

  it('sets isDirty to true after toggling a tool', () => {
    const { result } = renderHook(() => useItemSelection(items, items))

    act(() => {
      result.current.handleSelectItem('3', true)
    })

    expect(result.current.isDirty).toBe(true)
  })

  it('handleSelectItem enables a tool', () => {
    const { result } = renderHook(() => useItemSelection(items, items))

    act(() => {
      result.current.handleSelectItem('3', true)
    })

    expect(result.current.enabledIds.has('3')).toBe(true)
    expect(result.current.enabledCount).toBe(3)
  })

  it('handleSelectItem disables a tool', () => {
    const { result } = renderHook(() => useItemSelection(items, items))

    act(() => {
      result.current.handleSelectItem('1', false)
    })

    expect(result.current.enabledIds.has('1')).toBe(false)
    expect(result.current.enabledCount).toBe(1)
  })

  it('handleSelectAll enables all filtered items', () => {
    const { result } = renderHook(() => useItemSelection(items, items))

    act(() => {
      result.current.handleSelectAll(true)
    })

    expect(result.current.enabledCount).toBe(4)
    expect(result.current.allSelected).toBe(true)
  })

  it('handleSelectAll disables all filtered items', () => {
    const { result } = renderHook(() => useItemSelection(items, items))

    act(() => {
      result.current.handleSelectAll(false)
    })

    expect(result.current.enabledCount).toBe(0)
    expect(result.current.allSelected).toBe(false)
  })

  it('handleSelectAll only affects filtered items', () => {
    const filtered = items.slice(0, 2)
    const { result } = renderHook(() => useItemSelection(items, filtered))

    act(() => {
      result.current.handleSelectAll(false)
    })

    expect(result.current.enabledIds.has('1')).toBe(false)
    expect(result.current.enabledIds.has('2')).toBe(false)
    expect(result.current.enabledIds.has('3')).toBe(false)
    expect(result.current.enabledIds.has('4')).toBe(false)
  })

  it('resets to server state when allItems change', () => {
    const { result, rerender } = renderHook(
      ({ all, filtered }: { all: TestItem[]; filtered: TestItem[] }) => useItemSelection(all, filtered),
      { initialProps: { all: items, filtered: items } }
    )

    act(() => {
      result.current.handleSelectItem('3', true)
    })
    expect(result.current.isDirty).toBe(true)

    const updatedItems = items.map((i) => (i.id === '3' ? { ...i, enabled: true } : i))
    rerender({ all: updatedItems, filtered: updatedItems })

    expect(result.current.isDirty).toBe(false)
  })

  it('resetToServer discards local changes and restores server state', () => {
    const { result } = renderHook(() => useItemSelection(items, items))

    act(() => {
      result.current.handleSelectItem('1', false)
      result.current.handleSelectItem('3', true)
    })
    expect(result.current.isDirty).toBe(true)

    act(() => {
      result.current.resetToServer()
    })

    expect(result.current.isDirty).toBe(false)
    expect(result.current.enabledIds.has('1')).toBe(true)
    expect(result.current.enabledIds.has('3')).toBe(false)
  })
})

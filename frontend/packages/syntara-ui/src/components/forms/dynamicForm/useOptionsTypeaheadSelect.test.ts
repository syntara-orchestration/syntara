import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useOptionsTypeaheadSelect } from './useOptionsTypeaheadSelect'

const sampleOptions = [
  { label: 'Alpha', value: 'a' },
  { label: 'Beta', value: 'b' },
] as const

describe('useOptionsTypeaheadSelect', () => {
  it('uses loading placeholder and keeps the menu enabled while loading', () => {
    const onChange = vi.fn()
    const { result } = renderHook(() =>
      useOptionsTypeaheadSelect({
        options: [...sampleOptions],
        value: '',
        onChange,
        isMulti: false,
        isLoading: true,
      })
    )

    expect(result.current.placeholder).toBe('Loading options…')
    expect(result.current.toggleDisabled).toBe(false)
  })

  it('disables the toggle when loadErrorMessage is set', () => {
    const { result } = renderHook(() =>
      useOptionsTypeaheadSelect({
        options: [...sampleOptions],
        value: '',
        onChange: vi.fn(),
        isMulti: false,
        loadErrorMessage: 'Could not load options',
      })
    )

    expect(result.current.toggleDisabled).toBe(true)
    expect(result.current.placeholder).toBe('Could not load options')
  })

  it('invokes additional option onSelect from handleSelect', () => {
    const onChange = vi.fn()
    const onNone = vi.fn()
    const { result } = renderHook(() =>
      useOptionsTypeaheadSelect({
        options: [...sampleOptions],
        value: 'a',
        onChange,
        isMulti: false,
        additionalOptions: [{ key: '__none__', label: 'None', isSelected: false, onSelect: onNone }],
      })
    )

    act(() => {
      result.current.handleSelect(undefined, '__none__')
    })

    expect(onNone).toHaveBeenCalledTimes(1)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('clears single selection via clearSingleSelection', () => {
    const onChange = vi.fn()
    const { result } = renderHook(() =>
      useOptionsTypeaheadSelect({
        options: [...sampleOptions],
        value: 'a',
        onChange,
        isMulti: false,
      })
    )

    act(() => {
      result.current.clearSingleSelection()
    })

    expect(onChange).toHaveBeenCalledWith('')
    expect(result.current.isOpen).toBe(false)
  })

  it('reports empty filter message when options exist but none match', () => {
    const { result } = renderHook(() =>
      useOptionsTypeaheadSelect({
        options: [...sampleOptions],
        value: '',
        onChange: vi.fn(),
        isMulti: false,
      })
    )

    act(() => {
      result.current.handleFilterChange('zzz')
    })

    expect(result.current.emptyListMessage).toBe('No results match "zzz"')
    expect(result.current.showEmptyRow).toBe(true)
  })

  it('toggles multi-select values from handleSelect', () => {
    const onChange = vi.fn()
    const { result } = renderHook(() =>
      useOptionsTypeaheadSelect({
        options: [...sampleOptions],
        value: ['a'],
        onChange,
        isMulti: true,
      })
    )

    act(() => {
      result.current.handleSelect(undefined, 'b')
    })

    expect(onChange).toHaveBeenCalledWith(['a', 'b'])
  })
})

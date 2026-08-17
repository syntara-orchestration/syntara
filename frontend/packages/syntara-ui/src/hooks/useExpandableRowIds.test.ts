import { renderHook, act } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useExpandableRowIds } from './useExpandableRowIds'

describe('useExpandableRowIds', () => {
  it('starts with all rows collapsed', () => {
    const { result } = renderHook(() => useExpandableRowIds(['a', 'b']))

    expect(result.current.allRowsExpanded).toBe(false)
    expect(result.current.expandedRows.size).toBe(0)
  })

  it('expands and collapses a single row', () => {
    const { result } = renderHook(() => useExpandableRowIds(['a', 'b']))

    act(() => {
      result.current.handleToggleRow('a')
    })

    expect(result.current.expandedRows.has('a')).toBe(true)
    expect(result.current.allRowsExpanded).toBe(false)

    act(() => {
      result.current.handleToggleRow('a')
    })

    expect(result.current.expandedRows.has('a')).toBe(false)
  })

  it('expand-all toggles every row on the current page', () => {
    const { result } = renderHook(() => useExpandableRowIds(['a', 'b']))

    act(() => {
      result.current.handleCollapseAll()
    })

    expect(result.current.allRowsExpanded).toBe(true)
    expect(result.current.expandedRows).toEqual(new Set(['a', 'b']))

    act(() => {
      result.current.handleCollapseAll()
    })

    expect(result.current.allRowsExpanded).toBe(false)
    expect(result.current.expandedRows.size).toBe(0)
  })
})

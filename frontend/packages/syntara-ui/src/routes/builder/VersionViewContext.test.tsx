import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useIsVersionView } from './VersionViewContext'
import { VersionViewProvider } from './VersionViewProvider'

describe('VersionViewContext', () => {
  it('returns false by default (no provider)', () => {
    const { result } = renderHook(() => useIsVersionView())
    expect(result.current).toBe(false)
  })

  it('returns true when provider value is true', () => {
    const { result } = renderHook(() => useIsVersionView(), {
      wrapper: ({ children }) => <VersionViewProvider value={true}>{children}</VersionViewProvider>,
    })
    expect(result.current).toBe(true)
  })

  it('returns false when provider value is false', () => {
    const { result } = renderHook(() => useIsVersionView(), {
      wrapper: ({ children }) => <VersionViewProvider value={false}>{children}</VersionViewProvider>,
    })
    expect(result.current).toBe(false)
  })

  it('updates when provider value changes', () => {
    let currentValue = false

    const Wrapper = ({ children }: { children: React.ReactNode }) => (
      <VersionViewProvider value={currentValue}>{children}</VersionViewProvider>
    )

    const { result, rerender } = renderHook(() => useIsVersionView(), {
      wrapper: Wrapper,
    })

    expect(result.current).toBe(false)

    currentValue = true
    rerender()
    expect(result.current).toBe(true)
  })
})

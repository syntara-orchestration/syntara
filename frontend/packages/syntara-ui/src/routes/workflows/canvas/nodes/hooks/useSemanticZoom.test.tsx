import { renderHook } from '@testing-library/react'
import { ReactFlowProvider } from '@xyflow/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const viewportState = vi.hoisted(() => ({ zoom: 1 }))

vi.mock('@xyflow/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@xyflow/react')>()
  return {
    ...actual,
    useStore: (selector: (s: { transform: [number, number, number] }) => unknown) =>
      selector({ transform: [0, 0, viewportState.zoom] }),
  }
})

import { useSemanticZoom } from './useSemanticZoom'

const wrapper = ({ children }: { children: React.ReactNode }) => <ReactFlowProvider>{children}</ReactFlowProvider>

describe('useSemanticZoom', () => {
  afterEach(() => {
    viewportState.zoom = 1
  })

  it('returns false when summary is disabled', () => {
    viewportState.zoom = 0.5
    const { result } = renderHook(() => useSemanticZoom(false), { wrapper })

    expect(result.current).toBe(false)
  })

  it('returns false when zoom is above threshold with summary', () => {
    viewportState.zoom = 0.75
    const { result } = renderHook(() => useSemanticZoom(true), { wrapper })

    expect(result.current).toBe(false)
  })

  it('returns true when zoom is at the semantic threshold', () => {
    viewportState.zoom = 0.5
    const { result } = renderHook(() => useSemanticZoom(true), { wrapper })

    expect(result.current).toBe(true)
  })

  it('updates when crossing the semantic zoom threshold', () => {
    viewportState.zoom = 0.75
    const { rerender, result } = renderHook(() => useSemanticZoom(true), { wrapper })

    expect(result.current).toBe(false)

    viewportState.zoom = 0.5
    rerender()

    expect(result.current).toBe(true)

    viewportState.zoom = 0.75
    rerender()

    expect(result.current).toBe(false)
  })
})

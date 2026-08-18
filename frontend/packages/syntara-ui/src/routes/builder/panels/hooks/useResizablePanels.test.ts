import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useResizablePanels } from './useResizablePanels'

function mockContainer(width: number) {
  const el = document.createElement('div')
  vi.spyOn(el, 'getBoundingClientRect').mockReturnValue({
    width,
    height: 500,
    top: 0,
    left: 0,
    right: width,
    bottom: 500,
    x: 0,
    y: 0,
    toJSON: vi.fn(),
  })
  return el
}

describe('useResizablePanels', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  describe('defaults', () => {
    it('returns 3-panel defaults when panelCount is 3', () => {
      const { result } = renderHook(() => useResizablePanels({ panelCount: 3, workflowId: 'wf-1', nodeId: 'node-1' }))
      expect(result.current.widths).toEqual([33.3, 33.3, 33.4])
    })

    it('returns 2-panel defaults when panelCount is 2', () => {
      const { result } = renderHook(() => useResizablePanels({ panelCount: 2, workflowId: 'wf-1', nodeId: 'node-1' }))
      expect(result.current.widths).toEqual([33.3, 66.7])
    })
  })

  describe('localStorage restoration', () => {
    it('restores saved widths from localStorage', () => {
      localStorage.setItem('syntara-panel-sizes-wf-1-node-1', JSON.stringify([25, 50, 25]))
      const { result } = renderHook(() => useResizablePanels({ panelCount: 3, workflowId: 'wf-1', nodeId: 'node-1' }))
      expect(result.current.widths).toEqual([25, 50, 25])
    })

    it('falls back to defaults when saved panel count does not match', () => {
      localStorage.setItem('syntara-panel-sizes-wf-1-node-1', JSON.stringify([50, 50]))
      const { result } = renderHook(() => useResizablePanels({ panelCount: 3, workflowId: 'wf-1', nodeId: 'node-1' }))
      expect(result.current.widths).toEqual([33.3, 33.3, 33.4])
    })

    it('falls back to defaults when localStorage contains invalid JSON', () => {
      localStorage.setItem('syntara-panel-sizes-wf-1-node-1', 'not-json')
      const { result } = renderHook(() => useResizablePanels({ panelCount: 3, workflowId: 'wf-1', nodeId: 'node-1' }))
      expect(result.current.widths).toEqual([33.3, 33.3, 33.4])
    })

    it('falls back to defaults when workflowId is undefined', () => {
      localStorage.setItem('syntara-panel-sizes-wf-1-node-1', JSON.stringify([25, 50, 25]))
      const { result } = renderHook(() =>
        useResizablePanels({ panelCount: 3, workflowId: undefined, nodeId: 'node-1' })
      )
      expect(result.current.widths).toEqual([33.3, 33.3, 33.4])
    })

    it('falls back to defaults when nodeId is undefined', () => {
      localStorage.setItem('syntara-panel-sizes-wf-1-node-1', JSON.stringify([25, 50, 25]))
      const { result } = renderHook(() => useResizablePanels({ panelCount: 3, workflowId: 'wf-1', nodeId: undefined }))
      expect(result.current.widths).toEqual([33.3, 33.3, 33.4])
    })

    it('falls back to defaults when saved widths contain values below minimum', () => {
      localStorage.setItem('syntara-panel-sizes-wf-1-node-1', JSON.stringify([10, 45, 45]))
      const { result } = renderHook(() => useResizablePanels({ panelCount: 3, workflowId: 'wf-1', nodeId: 'node-1' }))
      expect(result.current.widths).toEqual([33.3, 33.3, 33.4])
    })
  })

  describe('handleResize', () => {
    it('adjusts adjacent panels when resizing', () => {
      const { result } = renderHook(() => useResizablePanels({ panelCount: 3, workflowId: 'wf-1', nodeId: 'node-1' }))

      Object.defineProperty(result.current.containerRef, 'current', { value: mockContainer(1000), writable: true })

      act(() => {
        result.current.handleResize(0, 100)
      })

      expect(result.current.widths[0]).toBeCloseTo(43.3, 1)
      expect(result.current.widths[1]).toBeCloseTo(23.3, 1)
      expect(result.current.widths[2]).toBeCloseTo(33.4, 1)
    })

    it('clamps panel widths to minimum 15%', () => {
      const { result } = renderHook(() => useResizablePanels({ panelCount: 3, workflowId: 'wf-1', nodeId: 'node-1' }))

      Object.defineProperty(result.current.containerRef, 'current', { value: mockContainer(1000), writable: true })

      act(() => {
        result.current.handleResize(0, 500)
      })

      expect(result.current.widths[1]).toBeGreaterThanOrEqual(15)
    })

    it('does nothing when container ref is null', () => {
      const { result } = renderHook(() => useResizablePanels({ panelCount: 3, workflowId: 'wf-1', nodeId: 'node-1' }))

      act(() => {
        result.current.handleResize(0, 100)
      })

      expect(result.current.widths).toEqual([33.3, 33.3, 33.4])
    })
  })

  describe('handleResizeEnd', () => {
    it('persists widths to localStorage', () => {
      const { result } = renderHook(() => useResizablePanels({ panelCount: 3, workflowId: 'wf-1', nodeId: 'node-1' }))

      act(() => {
        result.current.handleResizeEnd()
      })

      const stored = localStorage.getItem('syntara-panel-sizes-wf-1-node-1')
      expect(stored).not.toBeNull()
      expect(JSON.parse(stored!)).toEqual([33.3, 33.3, 33.4])
    })

    it('does not persist when workflowId is undefined', () => {
      const { result } = renderHook(() =>
        useResizablePanels({ panelCount: 3, workflowId: undefined, nodeId: 'node-1' })
      )

      act(() => {
        result.current.handleResizeEnd()
      })

      expect(localStorage).toHaveLength(0)
    })

    it('does not persist when nodeId is undefined', () => {
      const { result } = renderHook(() => useResizablePanels({ panelCount: 3, workflowId: 'wf-1', nodeId: undefined }))

      act(() => {
        result.current.handleResizeEnd()
      })

      expect(localStorage).toHaveLength(0)
    })
  })

  describe('panel count changes', () => {
    it('resets to defaults when panelCount changes from 3 to 2', () => {
      localStorage.setItem('syntara-panel-sizes-wf-1-node-1', JSON.stringify([25, 50, 25]))
      const { result, rerender } = renderHook(
        ({ panelCount }: { panelCount: 2 | 3 }) =>
          useResizablePanels({ panelCount, workflowId: 'wf-1', nodeId: 'node-1' }),
        { initialProps: { panelCount: 3 as 2 | 3 } }
      )

      expect(result.current.widths).toEqual([25, 50, 25])

      rerender({ panelCount: 2 })

      expect(result.current.widths).toEqual([33.3, 66.7])
    })

    it('resets to defaults when panelCount changes from 2 to 3', () => {
      const { result, rerender } = renderHook(
        ({ panelCount }: { panelCount: 2 | 3 }) =>
          useResizablePanels({ panelCount, workflowId: 'wf-1', nodeId: 'node-1' }),
        { initialProps: { panelCount: 2 as 2 | 3 } }
      )

      expect(result.current.widths).toEqual([33.3, 66.7])

      rerender({ panelCount: 3 })

      expect(result.current.widths).toEqual([33.3, 33.3, 33.4])
    })
  })

  describe('localStorage error handling', () => {
    it('handles localStorage.setItem throwing gracefully', () => {
      const setItemSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
        throw new Error('QuotaExceededError')
      })

      const { result } = renderHook(() => useResizablePanels({ panelCount: 3, workflowId: 'wf-1', nodeId: 'node-1' }))

      expect(() => {
        act(() => {
          result.current.handleResizeEnd()
        })
      }).not.toThrow()

      setItemSpy.mockRestore()
    })

    it('handles localStorage.getItem throwing gracefully', () => {
      const getItemSpy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
        throw new Error('SecurityError')
      })

      const { result } = renderHook(() => useResizablePanels({ panelCount: 3, workflowId: 'wf-1', nodeId: 'node-1' }))

      expect(result.current.widths).toEqual([33.3, 33.3, 33.4])

      getItemSpy.mockRestore()
    })
  })
})

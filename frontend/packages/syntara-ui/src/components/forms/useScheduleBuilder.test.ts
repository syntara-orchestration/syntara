import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useScheduleBuilder } from './useScheduleBuilder'

describe('useScheduleBuilder', () => {
  describe('initial state parsing', () => {
    it('parses a daily repeating interval with start date and time', () => {
      const { result } = renderHook(() => useScheduleBuilder('R/2026-01-15T10:30:00-05:00/P1D', 'America/New_York'))

      expect(result.current.state).toEqual(
        expect.objectContaining({
          startDate: '2026-01-15',
          startTime: '10:30',
          frequency: 'daily',
          intervalCount: 1,
          endDate: '',
        })
      )
    })

    it('parses a run-once interval as frequency "none"', () => {
      const { result } = renderHook(() => useScheduleBuilder('R1/2026-03-01T08:00:00Z/PT0S', 'UTC'))

      expect(result.current.state.frequency).toBe('none')
      expect(result.current.state.startDate).toBe('2026-03-01')
      expect(result.current.state.startTime).toBe('08:00')
    })

    it('parses an hourly interval with count > 1', () => {
      const { result } = renderHook(() => useScheduleBuilder('R/2026-06-10T14:00:00Z/PT3H', 'UTC'))

      expect(result.current.state.frequency).toBe('hourly')
      expect(result.current.state.intervalCount).toBe(3)
    })

    it('parses an interval with an end date', () => {
      const { result } = renderHook(() => useScheduleBuilder('R/2026-01-15T10:00:00Z/P1D/2026-02-15T23:59:59Z', 'UTC'))

      expect(result.current.state.startDate).toBe('2026-01-15')
      expect(result.current.state.endDate).toBe('2026-02-15')
    })

    it('handles an empty/invalid value gracefully', () => {
      const { result } = renderHook(() => useScheduleBuilder('', 'UTC'))

      expect(result.current.state.startDate).toBe('')
      expect(result.current.state.startTime).toBe('')
      expect(result.current.state.frequency).toBe('none')
    })

    it('leaves startDate/startTime empty when the start value has no time component', () => {
      const { result } = renderHook(() => useScheduleBuilder('R/2026-01-15/P1D', 'UTC'))

      expect(result.current.state.startDate).toBe('')
      expect(result.current.state.startTime).toBe('')
    })

    it('leaves startDate empty when the date portion is not in YYYY-MM-DD form', () => {
      const { result } = renderHook(() => useScheduleBuilder('R/abc-01-15T10:00:00Z/P1D', 'UTC'))

      expect(result.current.state.startDate).toBe('')
    })

    it('leaves startTime empty when the time portion is not in HH:MM form', () => {
      const { result } = renderHook(() => useScheduleBuilder('R/2026-01-15Txx:00:00Z/P1D', 'UTC'))

      expect(result.current.state.startTime).toBe('')
    })
  })

  describe('dispatch actions', () => {
    it('updates start date via SET_START_DATE', () => {
      const { result } = renderHook(() => useScheduleBuilder('R/2026-01-15T10:00:00Z/P1D', 'UTC'))

      act(() => {
        result.current.dispatch({ type: 'SET_START_DATE', payload: '2026-06-20' })
      })

      expect(result.current.state.startDate).toBe('2026-06-20')
    })

    it('updates start time via SET_START_TIME', () => {
      const { result } = renderHook(() => useScheduleBuilder('R/2026-01-15T10:00:00Z/P1D', 'UTC'))

      act(() => {
        result.current.dispatch({ type: 'SET_START_TIME', payload: '14:30' })
      })

      expect(result.current.state.startTime).toBe('14:30')
    })

    it('updates frequency via SET_FREQUENCY', () => {
      const { result } = renderHook(() => useScheduleBuilder('R/2026-01-15T10:00:00Z/P1D', 'UTC'))

      act(() => {
        result.current.dispatch({ type: 'SET_FREQUENCY', payload: 'weekly' })
      })

      expect(result.current.state.frequency).toBe('weekly')
    })

    it('clamps interval count to at least 1 via SET_INTERVAL_COUNT', () => {
      const { result } = renderHook(() => useScheduleBuilder('R/2026-01-15T10:00:00Z/P1D', 'UTC'))

      act(() => {
        result.current.dispatch({ type: 'SET_INTERVAL_COUNT', payload: 0 })
      })

      expect(result.current.state.intervalCount).toBe(1)

      act(() => {
        result.current.dispatch({ type: 'SET_INTERVAL_COUNT', payload: -5 })
      })

      expect(result.current.state.intervalCount).toBe(1)
    })

    it('returns the current state unchanged for an unrecognized action type', () => {
      const { result } = renderHook(() => useScheduleBuilder('R/2026-01-15T10:00:00Z/P1D', 'UTC'))
      const stateBefore = result.current.state

      act(() => {
        result.current.dispatch({ type: 'UNKNOWN' } as unknown as Parameters<typeof result.current.dispatch>[0])
      })

      expect(result.current.state).toEqual(stateBefore)
    })
  })

  describe('onChange emission', () => {
    it('emits a new interval string when state changes', () => {
      const onChange = vi.fn()
      const { result } = renderHook(() => useScheduleBuilder('R/2026-01-15T10:00:00+00:00/P1D', 'UTC', onChange))

      act(() => {
        result.current.dispatch({ type: 'SET_START_DATE', payload: '2026-03-01' })
      })

      expect(onChange).toHaveBeenCalledWith(expect.stringContaining('2026-03-01'))
    })

    it('emits a run-once interval when frequency is set to "none"', () => {
      const onChange = vi.fn()
      const { result } = renderHook(() => useScheduleBuilder('R/2026-01-15T10:00:00+00:00/P1D', 'UTC', onChange))

      act(() => {
        result.current.dispatch({ type: 'SET_FREQUENCY', payload: 'none' })
      })

      expect(onChange).toHaveBeenCalledWith(expect.stringMatching(/^R1\/.*\/PT0S$/))
    })

    it('appends end date to the interval string when endDate is set', () => {
      const onChange = vi.fn()
      const { result } = renderHook(() => useScheduleBuilder('R/2026-01-15T10:00:00+00:00/P1D', 'UTC', onChange))

      act(() => {
        result.current.dispatch({ type: 'SET_END_DATE', payload: '2026-12-31' })
      })

      expect(onChange).toHaveBeenCalledWith(expect.stringContaining('2026-12-31'))
    })

    it('does not emit when the composed value matches the current value', () => {
      const onChange = vi.fn()
      renderHook(() => useScheduleBuilder('R/2026-01-15T10:00:00+00:00/P1D', 'UTC', onChange))

      expect(onChange).not.toHaveBeenCalled()
    })

    it('does not emit a run-once interval when it matches the current value', () => {
      const onChange = vi.fn()
      renderHook(() => useScheduleBuilder('R1/2026-01-15T10:00:00+00:00/PT0S', 'UTC', onChange))

      expect(onChange).not.toHaveBeenCalled()
    })

    it('defaults start time to midnight when a start date is set without a time', () => {
      const onChange = vi.fn()
      const { result } = renderHook(() => useScheduleBuilder('', 'UTC', onChange))

      act(() => {
        result.current.dispatch({ type: 'SET_START_DATE', payload: '2026-06-20' })
      })

      expect(onChange).toHaveBeenCalledWith(expect.stringContaining('2026-06-20T00:00:00'))
    })
  })

  describe('external value re-sync', () => {
    it('re-initializes state when the value prop changes externally', () => {
      const { result, rerender } = renderHook(({ value }) => useScheduleBuilder(value, 'UTC'), {
        initialProps: { value: 'R/2026-01-15T10:00:00Z/P1D' },
      })

      expect(result.current.state.startDate).toBe('2026-01-15')
      expect(result.current.state.frequency).toBe('daily')

      rerender({ value: 'R/2026-06-01T08:00:00Z/PT2H' })

      expect(result.current.state.startDate).toBe('2026-06-01')
      expect(result.current.state.startTime).toBe('08:00')
      expect(result.current.state.frequency).toBe('hourly')
      expect(result.current.state.intervalCount).toBe(2)
    })

    it('does not re-initialize when the value matches the last emitted value', () => {
      const onChange = vi.fn()
      const { result, rerender } = renderHook(({ value }) => useScheduleBuilder(value, 'UTC', onChange), {
        initialProps: { value: 'R/2026-01-15T10:00:00+00:00/P1D' },
      })

      act(() => {
        result.current.dispatch({ type: 'SET_START_DATE', payload: '2026-03-01' })
      })

      const emittedValue = onChange.mock.calls.at(-1)?.[0] as string
      expect(emittedValue).toContain('2026-03-01')

      rerender({ value: emittedValue })

      expect(result.current.state.startDate).toBe('2026-03-01')
    })
  })
})

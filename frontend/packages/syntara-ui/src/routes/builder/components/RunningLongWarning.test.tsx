import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ExpectedDurationContext } from './expectedDurationContext'
import { RunningLongWarning } from './RunningLongWarning'

const startedAt = '2026-11-11T12:00:00Z'

describe('Running long warning', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(startedAt))
  })
  afterEach(() => vi.useRealTimers())

  it('appears at the step threshold while retaining the running state, and clears on completion', async () => {
    const { rerender } = render(<RunningLongWarning status="running" startedAt={startedAt} expectedDuration={2} />)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    await act(() => vi.advanceTimersByTime(1999))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    await act(() => vi.advanceTimersByTime(1))
    expect(screen.getByRole('status')).toHaveTextContent('Running long')
    expect(screen.getByRole('status')).toHaveAttribute('title', expect.stringContaining('does not stop the run'))
    rerender(
      <RunningLongWarning
        status="completed"
        startedAt={startedAt}
        completedAt={new Date().toISOString()}
        expectedDuration={2}
      />
    )
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('inherits the administrator default and lets a step override it', async () => {
    const { rerender } = render(
      <ExpectedDurationContext value={5}>
        <RunningLongWarning status="retrying" startedAt={startedAt} />
      </ExpectedDurationContext>
    )
    await act(() => vi.advanceTimersByTime(5000))
    expect(screen.getByText('Running long')).toBeInTheDocument()
    rerender(
      <ExpectedDurationContext value={5}>
        <RunningLongWarning status="retrying" startedAt={startedAt} expectedDuration={10} />
      </ExpectedDurationContext>
    )
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    await act(() => vi.advanceTimersByTime(5000))
    expect(screen.getByText('Running long')).toBeInTheDocument()
  })

  it.each(['pending', 'completed', 'failed', 'cancelled', 'skipped', 'waiting'] as const)(
    'does not warn for %s',
    async (status) => {
      render(<RunningLongWarning status={status} startedAt={startedAt} expectedDuration={1} />)
      await act(() => vi.advanceTimersByTime(10000))
      expect(screen.queryByRole('status')).not.toBeInTheDocument()
    }
  )

  it.each([undefined, 'invalid', '2026-11-11T13:00:00Z'])(
    'does not warn without an elapsed start time: %s',
    async (start) => {
      render(<RunningLongWarning status="running" startedAt={start} expectedDuration={1} />)
      await act(() => vi.advanceTimersByTime(2000))
      expect(screen.queryByRole('status')).not.toBeInTheDocument()
    }
  )

  it('does not warn when the inherited default is unavailable', async () => {
    render(<RunningLongWarning status="running" startedAt={startedAt} />)
    await act(() => vi.advanceTimersByTime(10000))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})

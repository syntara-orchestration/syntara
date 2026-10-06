import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FormPromptRunningLongAlert, FormPromptWaitingDuration } from './FormPromptTimeoutIndicators'

describe('FormPromptWaitingDuration', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-01T12:00:00.000Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows elapsed time and updates every second', () => {
    render(<FormPromptWaitingDuration waitingStartedAt="2026-10-01T11:59:30.000Z" isPending />)

    expect(screen.getByText('30s')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(screen.getByText('31s')).toBeInTheDocument()
  })

  it('renders nothing when not pending', () => {
    const { container } = render(
      <FormPromptWaitingDuration waitingStartedAt="2026-10-01T11:59:30.000Z" isPending={false} />
    )
    expect(container).toBeEmptyDOMElement()
  })
})

describe('FormPromptRunningLongAlert', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-01T12:00:00.000Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows warning after the configured expected duration', () => {
    const started = '2026-10-01T12:00:00.000Z'
    const thresholdSeconds = 600

    render(
      <FormPromptRunningLongAlert waitingStartedAt={started} runningLongThresholdSeconds={thresholdSeconds} isPending />
    )

    expect(screen.queryByText('Running long')).not.toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(thresholdSeconds * 1000)
    })

    expect(screen.getByText('Running long')).toBeInTheDocument()
  })
})

describe('FormPromptTimeoutIndicators accessibility', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-01T12:00:00.000Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('has no accessibility violations for waiting duration and running-long alert', async () => {
    const started = '2026-10-01T12:00:00.000Z'
    const thresholdSeconds = 600

    const { container } = render(
      <>
        <FormPromptWaitingDuration waitingStartedAt="2026-10-01T11:59:30.000Z" isPending />
        <FormPromptRunningLongAlert
          waitingStartedAt={started}
          runningLongThresholdSeconds={thresholdSeconds}
          isPending
        />
      </>
    )

    act(() => {
      vi.advanceTimersByTime(thresholdSeconds * 1000)
    })

    vi.useRealTimers()
    expect(await axe(container)).toHaveNoViolations()
  })
})

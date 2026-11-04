import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FormPromptWaitingDuration } from './FormPromptWaitingDuration'

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

  it('has no accessibility violations', async () => {
    const { container } = render(<FormPromptWaitingDuration waitingStartedAt="2026-10-01T11:59:30.000Z" isPending />)

    vi.useRealTimers()
    expect(await axe(container)).toHaveNoViolations()
  })
})

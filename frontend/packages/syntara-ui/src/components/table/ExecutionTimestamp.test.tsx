import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { ExecutionTimeRange, ExecutionTimestamp } from './ExecutionTimestamp'

describe('ExecutionTimestamp', () => {
  it('renders a full date and time for a valid date', () => {
    render(<ExecutionTimestamp dateString="2026-01-26T15:30:45Z" />)
    expect(screen.getByText(/Jan.*26.*2026/i)).toBeInTheDocument()
  })

  it('renders time only when timeOnly is set', () => {
    render(<ExecutionTimestamp dateString="2026-01-26T15:30:45Z" timeOnly />)
    expect(screen.queryByText(/2026/)).not.toBeInTheDocument()
  })

  it('renders nothing for a null date', () => {
    const { container } = render(<ExecutionTimestamp dateString={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing for an invalid date', () => {
    const { container } = render(<ExecutionTimestamp dateString="not-a-date" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ExecutionTimestamp dateString="2026-01-26T15:30:45Z" />)
    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('ExecutionTimeRange', () => {
  it('renders nothing when there is no start time', () => {
    const { container } = render(<ExecutionTimeRange startedAt={null} completedAt={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders only the start timestamp when there is no end time', () => {
    render(<ExecutionTimeRange startedAt="2026-04-16T10:00:00Z" completedAt={null} />)
    expect(screen.getByText(/Apr.*16.*2026/i)).toBeInTheDocument()
  })

  it('collapses the start to time-only when start and end share a calendar day', () => {
    render(<ExecutionTimeRange startedAt="2026-04-16T10:00:00Z" completedAt="2026-04-16T10:01:30Z" />)
    // Only the end should carry a full date; the start collapses to time-only.
    expect(screen.getAllByText(/2026/)).toHaveLength(1)
  })

  it('shows full dates for both sides when start and end span different days', () => {
    render(<ExecutionTimeRange startedAt="2026-04-15T12:00:00Z" completedAt="2026-04-17T12:00:00Z" />)
    expect(screen.getAllByText(/2026/)).toHaveLength(2)
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <ExecutionTimeRange startedAt="2026-04-16T10:00:00Z" completedAt="2026-04-16T10:01:30Z" />
    )
    expect(await axe(container)).toHaveNoViolations()
  })
})

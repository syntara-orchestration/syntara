import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { DateCell } from './DateCell'

describe('DateCell', () => {
  it('renders formatted date with abbreviated month name', () => {
    render(<DateCell dateString="2026-05-27T09:55:01Z" />)
    const cell = screen.getByText(/May.*27.*2026/i)
    expect(cell).toBeInTheDocument()
  })

  it('does not render numeric month format', () => {
    render(<DateCell dateString="2026-05-27T09:55:01Z" />)
    expect(screen.queryByText(/^5\/27\/2026/)).not.toBeInTheDocument()
  })

  it('renders "-" for null dateString', () => {
    render(<DateCell dateString={null} />)
    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('renders "-" for undefined dateString', () => {
    render(<DateCell />)
    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('renders "-" for empty string', () => {
    render(<DateCell dateString="" />)
    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('renders "-" for invalid date string', () => {
    render(<DateCell dateString="not-a-date" />)
    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('renders a semantic <time> element with a datetime attribute for a valid date', () => {
    render(<DateCell dateString="2026-05-27T09:55:01Z" />)
    const timeEl = screen.getByText(/May.*27.*2026/i)
    expect(timeEl.tagName).toBe('TIME')
    expect(timeEl).toHaveAttribute('datetime', '2026-05-27T09:55:01.000Z')
  })

  it('has no accessibility violations with a valid date', async () => {
    const { container } = render(<DateCell dateString="2026-01-15T14:30:00Z" />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with null date', async () => {
    const { container } = render(<DateCell dateString={null} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('handles re-render with same props (cache hit)', () => {
    const { rerender } = render(<DateCell dateString="2026-05-27T09:55:01Z" />)
    rerender(<DateCell dateString="2026-05-27T09:55:01Z" />)
    expect(screen.getByText(/May.*27.*2026/i)).toBeInTheDocument()
  })

  it('handles re-render with changed props (cache invalidation)', () => {
    const { rerender } = render(<DateCell dateString="2026-05-27T09:55:01Z" />)
    rerender(<DateCell dateString="2026-06-15T10:00:00Z" />)
    expect(screen.getByText(/Jun.*15.*2026/i)).toBeInTheDocument()
  })

  it('handles re-render from valid date to null', () => {
    const { rerender } = render(<DateCell dateString="2026-05-27T09:55:01Z" />)
    rerender(<DateCell dateString={null} />)
    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('handles re-render from null to valid date', () => {
    const { rerender } = render(<DateCell dateString={null} />)
    rerender(<DateCell dateString="2026-03-10T08:00:00Z" />)
    expect(screen.getByText(/Mar.*10.*2026/i)).toBeInTheDocument()
  })
})

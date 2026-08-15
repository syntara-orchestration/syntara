import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

vi.mock('./historyDateUtils', () => ({
  formatHistoryDateTime: vi.fn((iso: string) => `formatted:${iso}`),
}))

import { VersionInfoCard } from './VersionInfoCard'

describe('VersionInfoCard', () => {
  it('returns null when all props are null/undefined', () => {
    render(<VersionInfoCard />)

    expect(screen.queryByRole('article')).not.toBeInTheDocument()
  })

  it('returns null when all props are explicitly null', () => {
    render(<VersionInfoCard title={null} date={null} description={null} />)

    expect(screen.queryByRole('article')).not.toBeInTheDocument()
  })

  it('shows formatted date as title when no title prop is provided', () => {
    render(<VersionInfoCard date="2026-05-19T21:59:00.000Z" />)

    expect(screen.getByText('formatted:2026-05-19T21:59:00.000Z')).toBeInTheDocument()
  })

  it('shows title prop as title when provided', () => {
    render(<VersionInfoCard title="v2.0 Release" date="2026-05-19T21:59:00.000Z" />)

    expect(screen.getByText('v2.0 Release')).toBeInTheDocument()
  })

  it('shows created date in card body when title is provided', () => {
    render(<VersionInfoCard title="v2.0 Release" date="2026-05-19T21:59:00.000Z" />)

    expect(screen.getByText('v2.0 Release')).toBeInTheDocument()
    expect(screen.getByText('Created')).toBeInTheDocument()
    expect(screen.getByText(/May.*19.*2026/i)).toBeInTheDocument()
  })

  it('does not show date as subtitle when no title prop is provided', () => {
    render(<VersionInfoCard date="2026-05-19T21:59:00.000Z" />)

    expect(screen.queryByText('Created')).not.toBeInTheDocument()
  })

  it('shows description when provided', () => {
    render(<VersionInfoCard description="Fixed a critical bug" />)

    expect(screen.getByText('Fixed a critical bug')).toBeInTheDocument()
  })

  it('renders all sections when all props are provided', () => {
    render(<VersionInfoCard title="v2.0 Release" date="2026-05-19T21:59:00.000Z" description="Major update" />)

    expect(screen.getByText('v2.0 Release')).toBeInTheDocument()
    expect(screen.getByText('Created')).toBeInTheDocument()
    expect(screen.getByText(/May.*19.*2026/i)).toBeInTheDocument()
    expect(screen.getByText('Major update')).toBeInTheDocument()
  })

  it('does not render date subtitle when date is null', () => {
    render(<VersionInfoCard title="v2.0 Release" />)

    expect(screen.getByText('v2.0 Release')).toBeInTheDocument()
    expect(screen.queryByText('Created')).not.toBeInTheDocument()
  })

  it('renders Published/Unpublished rows via PF Timestamp', () => {
    render(
      <VersionInfoCard
        title="v2.0 Release"
        publishedAt="2026-06-01T10:00:00.000Z"
        unpublishedAt="2026-06-10T10:00:00.000Z"
      />
    )

    expect(screen.getByText('Published')).toBeInTheDocument()
    expect(screen.getByText(/Jun 1,\s*2026/i)).toBeInTheDocument()
    expect(screen.getByText('Unpublished')).toBeInTheDocument()
    expect(screen.getByText(/Jun 10,\s*2026/i)).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <VersionInfoCard title="v2.0 Release" date="2026-05-19T21:59:00.000Z" description="Major update" />
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})

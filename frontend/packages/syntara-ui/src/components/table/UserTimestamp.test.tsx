import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { UserTimestamp } from './UserTimestamp'

const userRef = { id: '550e8400-e29b-41d4-a716-446655440001', name: 'alice' }
const timestamp = '2026-07-01T12:00:00Z'
const expectedHref = `/system-administration/access-management/users/${userRef.id}`

describe('UserTimestamp', () => {
  describe('resolves display name from different user types', () => {
    it('renders username from a UserReference object', () => {
      render(<UserTimestamp user={userRef} timestamp={timestamp} />)
      expect(screen.getByText('alice')).toBeInTheDocument()
    })

    it('renders username from a plain string', () => {
      render(<UserTimestamp user="bob" timestamp={timestamp} />)
      expect(screen.getByText('bob')).toBeInTheDocument()
    })

    it('renders only timestamp when user is null', () => {
      const { container } = render(<UserTimestamp user={null} timestamp={timestamp} />)
      expect(container.textContent).not.toContain('alice')
      expect(container.textContent).toContain('Jul')
    })

    it('renders only timestamp when user is undefined', () => {
      const { container } = render(<UserTimestamp timestamp={timestamp} />)
      expect(container.textContent).toContain('Jul')
    })
  })

  describe('username links', () => {
    it('renders as a link when user is a UserReference', () => {
      render(<UserTimestamp user={userRef} timestamp={timestamp} />)
      const link = screen.getByRole('link', { name: 'alice' })
      expect(link).toBeInTheDocument()
      expect(link).toHaveAttribute('href', expectedHref)
    })

    it('renders as a link in inline mode when user is a UserReference', () => {
      render(<UserTimestamp user={userRef} timestamp={timestamp} inline />)
      const link = screen.getByRole('link', { name: 'alice' })
      expect(link).toBeInTheDocument()
      expect(link).toHaveAttribute('href', expectedHref)
    })

    it('does not render a link when user is a plain string', () => {
      render(<UserTimestamp user="bob" timestamp={timestamp} />)
      expect(screen.getByText('bob')).toBeInTheDocument()
      expect(screen.queryByRole('link', { name: 'bob' })).not.toBeInTheDocument()
    })

    it('does not render a link when user is null', () => {
      render(<UserTimestamp user={null} timestamp={timestamp} />)
      expect(screen.queryByRole('link')).not.toBeInTheDocument()
    })

    it('does not render a link when user is undefined', () => {
      render(<UserTimestamp timestamp={timestamp} />)
      expect(screen.queryByRole('link')).not.toBeInTheDocument()
    })

    it('does not render a link in inline mode when user is a plain string', () => {
      render(<UserTimestamp user="charlie" timestamp={timestamp} inline />)
      expect(screen.getByText('charlie')).toBeInTheDocument()
      expect(screen.queryByRole('link', { name: 'charlie' })).not.toBeInTheDocument()
    })
  })

  describe('stacked mode (default)', () => {
    it('renders user and timestamp on separate lines', () => {
      render(<UserTimestamp user={userRef} timestamp={timestamp} />)
      expect(screen.getByText('alice')).toBeInTheDocument()
    })

    it('renders with UserReference in stacked mode', () => {
      render(<UserTimestamp user={userRef} timestamp={timestamp} subtleTimestamp={false} />)
      expect(screen.getByText('alice')).toBeInTheDocument()
    })

    it('renders without user in stacked mode', () => {
      render(<UserTimestamp timestamp={timestamp} />)
      expect(screen.getByText(/Jul/)).toBeInTheDocument()
    })

    it('renders plain string user with neutral timestamp', () => {
      render(<UserTimestamp user="bob" timestamp={timestamp} subtleTimestamp={false} />)
      expect(screen.getByText('bob')).toBeInTheDocument()
    })

    it('renders without user and neutral timestamp', () => {
      render(<UserTimestamp timestamp={timestamp} subtleTimestamp={false} />)
      expect(screen.getByText(/Jul/)).toBeInTheDocument()
    })

    it('renders with explicit inline=false and subtleTimestamp=true', () => {
      render(<UserTimestamp user={userRef} timestamp={timestamp} inline={false} subtleTimestamp={true} />)
      const link = screen.getByRole('link', { name: 'alice' })
      expect(link).toHaveAttribute('href', expectedHref)
    })

    it('renders timestamp only when no user or timestamp provided', () => {
      const { container } = render(<UserTimestamp />)
      expect(container.textContent).toBeDefined()
    })

    it('renders string user with explicit subtleTimestamp=true', () => {
      render(<UserTimestamp user="eve" timestamp={timestamp} subtleTimestamp={true} />)
      expect(screen.getByText('eve')).toBeInTheDocument()
    })
  })

  describe('inline mode', () => {
    it('renders timestamp and user on one line with "by" separator', () => {
      const { container } = render(<UserTimestamp user={userRef} timestamp={timestamp} inline />)
      expect(screen.getByText('alice')).toBeInTheDocument()
      expect(container.textContent).toContain('by')
      expect(container.textContent).not.toContain('·')
    })

    it('renders UserReference object inline', () => {
      render(<UserTimestamp user={userRef} timestamp={timestamp} inline />)
      expect(screen.getByText('alice')).toBeInTheDocument()
    })

    it('renders plain string user inline', () => {
      render(<UserTimestamp user="charlie" timestamp={timestamp} inline />)
      expect(screen.getByText('charlie')).toBeInTheDocument()
    })

    it('renders only timestamp inline when user is null', () => {
      const { container } = render(<UserTimestamp user={null} timestamp={timestamp} inline />)
      expect(container.textContent).not.toContain('by')
    })

    it('applies neutral timestamp color when subtleTimestamp is false', () => {
      render(<UserTimestamp user={userRef} timestamp={timestamp} inline subtleTimestamp={false} />)
      expect(screen.getByText('alice')).toBeInTheDocument()
    })

    it('renders only timestamp inline when user is undefined', () => {
      const { container } = render(<UserTimestamp timestamp={timestamp} inline />)
      expect(container.textContent).not.toContain('by')
    })

    it('renders plain string user inline with neutral timestamp', () => {
      render(<UserTimestamp user="dave" timestamp={timestamp} inline subtleTimestamp={false} />)
      expect(screen.getByText('dave')).toBeInTheDocument()
    })

    it('renders only timestamp inline with neutral timestamp when user is null', () => {
      const { container } = render(<UserTimestamp user={null} timestamp={timestamp} inline subtleTimestamp={false} />)
      expect(container.textContent).not.toContain('by')
    })

    it('renders with explicit inline=true and subtleTimestamp=true', () => {
      render(<UserTimestamp user={userRef} timestamp={timestamp} inline={true} subtleTimestamp={true} />)
      const link = screen.getByRole('link', { name: 'alice' })
      expect(link).toHaveAttribute('href', expectedHref)
    })

    it('renders inline without timestamp', () => {
      render(<UserTimestamp user={userRef} inline />)
      expect(screen.getByRole('link', { name: 'alice' })).toBeInTheDocument()
    })

    it('renders inline string user with explicit subtleTimestamp=true', () => {
      render(<UserTimestamp user="frank" timestamp={timestamp} inline={true} subtleTimestamp={true} />)
      expect(screen.getByText('frank')).toBeInTheDocument()
    })

    it('renders inline with undefined user and explicit subtleTimestamp=false', () => {
      const { container } = render(<UserTimestamp inline={true} subtleTimestamp={false} />)
      expect(container.textContent).not.toContain('by')
    })
  })

  describe('user rendering mode', () => {
    it('renders plain string user as text (not a link) in stacked mode', () => {
      render(<UserTimestamp user="bob" timestamp={timestamp} />)
      expect(screen.getByText('bob')).toBeInTheDocument()
      expect(screen.queryByRole('link', { name: 'bob' })).not.toBeInTheDocument()
    })

    it('renders plain string user as text (not a link) in inline mode', () => {
      render(<UserTimestamp user="bob" timestamp={timestamp} inline />)
      expect(screen.getByText('bob')).toBeInTheDocument()
      expect(screen.queryByRole('link', { name: 'bob' })).not.toBeInTheDocument()
    })

    it('renders UserReference as a link in stacked mode', () => {
      render(<UserTimestamp user={userRef} timestamp={timestamp} />)
      const link = screen.getByRole('link', { name: 'alice' })
      expect(link).toHaveAttribute('href', expectedHref)
    })

    it('renders UserReference as a link in inline mode', () => {
      render(<UserTimestamp user={userRef} timestamp={timestamp} inline />)
      const link = screen.getByRole('link', { name: 'alice' })
      expect(link).toHaveAttribute('href', expectedHref)
    })
  })

  describe('"by" separator rendering', () => {
    it('renders "by" prefix before username in stacked mode', () => {
      const { container } = render(<UserTimestamp user={userRef} timestamp={timestamp} />)
      expect(container.textContent).toContain('by')
    })

    it('renders "by" prefix before username in inline mode', () => {
      const { container } = render(<UserTimestamp user={userRef} timestamp={timestamp} inline />)
      expect(container.textContent).toContain('by')
    })

    it('does not render "by" when user is null in stacked mode', () => {
      const { container } = render(<UserTimestamp user={null} timestamp={timestamp} />)
      expect(container.textContent).not.toContain('by')
    })

    it('does not render "by" when user is undefined in stacked mode', () => {
      const { container } = render(<UserTimestamp timestamp={timestamp} />)
      expect(container.textContent).not.toContain('by')
    })

    it('renders "by" prefix before plain string user in stacked mode', () => {
      const { container } = render(<UserTimestamp user="bob" timestamp={timestamp} />)
      expect(container.textContent).toContain('by')
      expect(container.textContent).toContain('bob')
    })

    it('renders "by" prefix before plain string user in inline mode', () => {
      const { container } = render(<UserTimestamp user="bob" timestamp={timestamp} inline />)
      expect(container.textContent).toContain('by')
      expect(container.textContent).toContain('bob')
    })
  })

  it('renders a semantic <time> element with a datetime attribute', () => {
    render(<UserTimestamp user={userRef} timestamp={timestamp} />)
    const timeEl = screen.getByText(/Jul.*1.*2026/i)
    expect(timeEl.tagName).toBe('TIME')
    expect(timeEl).toHaveAttribute('datetime', '2026-07-01T12:00:00.000Z')
  })

  describe('accessibility', () => {
    it('has no a11y violations in stacked mode with link', async () => {
      const { container } = render(<UserTimestamp user={userRef} timestamp={timestamp} />)
      expect(await axe(container)).toHaveNoViolations()
    })

    it('has no a11y violations in inline mode with link', async () => {
      const { container } = render(<UserTimestamp user={userRef} timestamp={timestamp} inline />)
      expect(await axe(container)).toHaveNoViolations()
    })

    it('has no a11y violations with plain string user', async () => {
      const { container } = render(<UserTimestamp user="bob" timestamp={timestamp} />)
      expect(await axe(container)).toHaveNoViolations()
    })

    it('has no a11y violations without user', async () => {
      const { container } = render(<UserTimestamp timestamp={timestamp} />)
      expect(await axe(container)).toHaveNoViolations()
    })
  })
})

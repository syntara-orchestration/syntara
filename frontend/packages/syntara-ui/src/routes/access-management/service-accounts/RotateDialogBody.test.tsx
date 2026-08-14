import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { RotateDialogBody } from './RotateDialogBody'
import { GRACE_PERIOD_HELP } from './serviceAccountFieldHelpText'
import type { ServiceAccountCredentialRead } from './serviceAccountTypes'

const mockCredential: ServiceAccountCredentialRead = {
  id: 'cred-1',
  identifier: 'test-cred',
  credential_type: 'client_credentials',
  service_account_id: 'sa-1',
  status: 'active',
  grace_period_seconds: 3600,
  expires_at: null,
  last_used_at: null,
  created_at: '2026-07-14T12:00:00Z',
  updated_at: '2026-07-14T12:00:00Z',
  created_by: 'user-1',
  updated_by: 'user-1',
}

describe('RotateDialogBody', () => {
  const defaultProps = {
    credential: mockCredential,
    gracePeriod: 3600,
    onGracePeriodChange: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders credential identifier in the description', () => {
    render(<RotateDialogBody {...defaultProps} />)

    expect(screen.getByText('test-cred')).toBeInTheDocument()
  })

  it('renders the grace period selector with the default option', () => {
    render(<RotateDialogBody {...defaultProps} />)

    expect(screen.getByRole('button', { name: '1 hour' })).toBeInTheDocument()
  })

  it('shows grace period help on click', async () => {
    const user = userEvent.setup()
    render(<RotateDialogBody {...defaultProps} />)

    await user.click(screen.getByRole('button', { name: 'More info for Current secret grace period' }))
    expect(screen.getByText(GRACE_PERIOD_HELP)).toBeInTheDocument()
  })

  it('calls onGracePeriodChange when a different option is selected', async () => {
    const user = userEvent.setup()
    render(<RotateDialogBody {...defaultProps} />)

    await user.click(screen.getByRole('button', { name: '1 hour' }))
    await user.click(screen.getByRole('option', { name: '24 hours' }))

    expect(defaultProps.onGracePeriodChange).toHaveBeenCalledWith(86400)
  })

  it('does not show active grace period warning when credential has no old_secret_valid_until', () => {
    render(<RotateDialogBody {...defaultProps} />)

    expect(screen.queryByText('Active grace period will be replaced')).not.toBeInTheDocument()
  })

  describe('active grace period warning', () => {
    beforeEach(() => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date('2026-07-15T12:00:00Z'))
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    it('shows warning when credential has an active grace period', () => {
      const credWithGrace: ServiceAccountCredentialRead = {
        ...mockCredential,
        old_secret_valid_until: '2026-07-15T15:00:00Z',
      }

      render(<RotateDialogBody {...defaultProps} credential={credWithGrace} />)

      expect(screen.getByText('Active grace period will be replaced')).toBeInTheDocument()
      expect(screen.getByText('3h')).toBeInTheDocument()
    })

    it('does not show warning when grace period has already expired', () => {
      const credWithExpiredGrace: ServiceAccountCredentialRead = {
        ...mockCredential,
        old_secret_valid_until: '2026-07-15T11:00:00Z',
      }

      render(<RotateDialogBody {...defaultProps} credential={credWithExpiredGrace} />)

      expect(screen.queryByText('Active grace period will be replaced')).not.toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations in default state', async () => {
      const { container } = render(<RotateDialogBody {...defaultProps} />)

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations when active grace period warning is shown', async () => {
      const futureDate = new Date(Date.now() + 3 * 60 * 60 * 1000).toISOString()
      const credWithGrace: ServiceAccountCredentialRead = {
        ...mockCredential,
        old_secret_valid_until: futureDate,
      }

      const { container } = render(<RotateDialogBody {...defaultProps} credential={credWithGrace} />)

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})

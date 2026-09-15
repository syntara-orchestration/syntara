import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { CreateCredentialModal } from './CreateCredentialModal'

describe('CreateCredentialModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    onSubmit: vi.fn(),
    isPending: false,
    maxLifetimeDays: 180,
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the modal title', () => {
    render(<CreateCredentialModal {...defaultProps} />)

    expect(screen.getByRole('heading', { name: 'Create credential' })).toBeInTheDocument()
  })

  it('renders the expiration date field', () => {
    render(<CreateCredentialModal {...defaultProps} />)

    expect(screen.getByText('Expiration date')).toBeInTheDocument()
  })

  it('shows maximum lifetime helper text', () => {
    render(<CreateCredentialModal {...defaultProps} />)

    expect(screen.getByText(/Maximum lifetime: 180 days/)).toBeInTheDocument()
  })

  it('shows unlimited helper text when maxLifetimeDays is 0', () => {
    render(<CreateCredentialModal {...defaultProps} maxLifetimeDays={0} />)

    expect(screen.getByText('No maximum lifetime configured')).toBeInTheDocument()
  })

  it('calls onSubmit with ISO date when Create is clicked', async () => {
    const user = userEvent.setup()
    render(<CreateCredentialModal {...defaultProps} />)

    await user.click(screen.getByRole('button', { name: 'Create' }))

    expect(defaultProps.onSubmit).toHaveBeenCalledTimes(1)
    const arg = defaultProps.onSubmit.mock.calls[0][0] as string
    expect(arg).toMatch(/^\d{4}-\d{2}-\d{2}T00:00:00Z$/)
  })

  it('calls onClose when Cancel is clicked', async () => {
    const user = userEvent.setup()
    render(<CreateCredentialModal {...defaultProps} />)

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
  })

  it('disables Create button when isPending is true', () => {
    render(<CreateCredentialModal {...defaultProps} isPending={true} />)

    expect(screen.getByRole('button', { name: /Create/ })).toBeDisabled()
  })

  it('disables Cancel button when isPending is true', () => {
    render(<CreateCredentialModal {...defaultProps} isPending={true} />)

    expect(screen.getByRole('button', { name: /Cancel/ })).toBeDisabled()
  })

  it('does not call onSubmit when there is a validation error', async () => {
    const user = userEvent.setup()
    render(<CreateCredentialModal {...defaultProps} />)

    const dateInput = screen.getByLabelText('Expiration date')
    await user.clear(dateInput)
    await user.type(dateInput, 'not-a-date')

    await user.click(screen.getByRole('button', { name: 'Create' }))

    expect(defaultProps.onSubmit).not.toHaveBeenCalled()
  })

  it('does not render content when closed', () => {
    render(<CreateCredentialModal {...defaultProps} isOpen={false} />)

    expect(screen.queryByText('Create credential')).not.toBeInTheDocument()
  })

  it('shows description text about secret being shown only once', () => {
    render(<CreateCredentialModal {...defaultProps} />)

    expect(screen.getByText(/The secret is shown only once after creation/)).toBeInTheDocument()
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(<CreateCredentialModal {...defaultProps} />)

      await waitFor(async () => {
        const results = await axe(container)
        expect(results).toHaveNoViolations()
      })
    })

    it('has no accessibility violations when pending', async () => {
      const { container } = render(<CreateCredentialModal {...defaultProps} isPending={true} />)

      await waitFor(async () => {
        const results = await axe(container)
        expect(results).toHaveNoViolations()
      })
    })

    it('has no accessibility violations with unlimited lifetime', async () => {
      const { container } = render(<CreateCredentialModal {...defaultProps} maxLifetimeDays={0} />)

      await waitFor(async () => {
        const results = await axe(container)
        expect(results).toHaveNoViolations()
      })
    })
  })
})

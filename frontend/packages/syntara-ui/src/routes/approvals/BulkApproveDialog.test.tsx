import { render, screen } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { BulkApproveDialog } from './BulkDecisionDialog'

describe('BulkApproveDialog', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    onConfirm: vi.fn(),
    approvalCount: 2,
  }

  it('renders modal with correct title', () => {
    render(<BulkApproveDialog {...defaultProps} />)

    expect(screen.getByRole('dialog', { name: /approve 2 approval steps/i })).toBeInTheDocument()
  })

  it('renders singular title for single approval', () => {
    render(<BulkApproveDialog {...defaultProps} approvalCount={1} />)

    expect(screen.getByRole('dialog', { name: /approve 1 approval step$/i })).toBeInTheDocument()
  })

  it('displays approval count message', () => {
    render(<BulkApproveDialog {...defaultProps} />)

    expect(screen.getByText(/You are about to approve 2 approval steps/)).toBeInTheDocument()
  })

  it('shows note field by default', () => {
    render(<BulkApproveDialog {...defaultProps} />)

    expect(screen.getByPlaceholderText(/optional note for these approvals/i)).toBeInTheDocument()
  })

  it('calls onConfirm with null when note is not added', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()

    render(<BulkApproveDialog {...defaultProps} onConfirm={onConfirm} />)

    await user.click(screen.getByRole('button', { name: /approve/i }))

    expect(onConfirm).toHaveBeenCalledWith(null)
  })

  it('calls onConfirm with note text when note is added', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    render(<BulkApproveDialog {...defaultProps} onConfirm={onConfirm} />)

    const noteField = screen.getByPlaceholderText(/optional note for these approvals/i)
    await user.type(noteField, 'Test note for approval')

    await user.click(screen.getByRole('button', { name: /approve/i }))

    expect(onConfirm).toHaveBeenCalledWith('Test note for approval')
  })

  it('calls onConfirm with null when note field is empty', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()

    render(<BulkApproveDialog {...defaultProps} onConfirm={onConfirm} />)

    await user.click(screen.getByRole('button', { name: /approve/i }))

    expect(onConfirm).toHaveBeenCalledWith(null)
  })

  it('trims whitespace from note', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    render(<BulkApproveDialog {...defaultProps} onConfirm={onConfirm} />)

    const noteField = screen.getByPlaceholderText(/optional note for these approvals/i)
    await user.type(noteField, '  Test note  ')

    await user.click(screen.getByRole('button', { name: /approve/i }))

    expect(onConfirm).toHaveBeenCalledWith('Test note')
  })

  it('calls onClose when cancel button clicked', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()

    render(<BulkApproveDialog {...defaultProps} onClose={onClose} />)

    await user.click(screen.getByRole('button', { name: /cancel/i }))

    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('disables buttons when isLoading is true', () => {
    render(<BulkApproveDialog {...defaultProps} isLoading={true} />)

    expect(screen.getByRole('button', { name: /approve/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeDisabled()
  })

  it('does not render when isOpen is false', () => {
    render(<BulkApproveDialog {...defaultProps} isOpen={false} />)

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('displays approval count in message', () => {
    render(<BulkApproveDialog {...defaultProps} />)

    expect(screen.getByText(/You are about to approve 2 approval steps/)).toBeInTheDocument()
  })

  it('displays singular form for single approval', () => {
    render(<BulkApproveDialog {...defaultProps} approvalCount={1} />)

    expect(screen.getByText(/You are about to approve 1 approval step\./)).toBeInTheDocument()
  })

  it('displays plural form for multiple approvals', () => {
    render(<BulkApproveDialog {...defaultProps} approvalCount={2} />)

    expect(screen.getByText(/You are about to approve 2 approval steps/)).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<BulkApproveDialog {...defaultProps} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

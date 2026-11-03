import { render, screen, within } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { BulkRejectDialog } from './BulkDecisionDialog'

describe('BulkRejectDialog', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    onConfirm: vi.fn(),
    approvalCount: 2,
  }

  it('renders modal with correct title', () => {
    render(<BulkRejectDialog {...defaultProps} />)

    expect(screen.getByRole('dialog', { name: /reject 2 approval steps/i })).toBeInTheDocument()
  })

  it('renders singular title for single approval', () => {
    render(<BulkRejectDialog {...defaultProps} approvalCount={1} />)

    expect(screen.getByRole('dialog', { name: /reject 1 approval step$/i })).toBeInTheDocument()
  })

  it('displays approval count message', () => {
    render(<BulkRejectDialog {...defaultProps} />)

    expect(screen.getByText(/You are about to reject 2 approval steps/)).toBeInTheDocument()
  })

  it('renders optional rejection note field', () => {
    render(<BulkRejectDialog {...defaultProps} />)

    const field = screen.getByLabelText(/rejection note/i)
    expect(field).toBeInTheDocument()
    expect(field).not.toBeRequired()
  })

  it('enables reject button even when note is empty', () => {
    render(<BulkRejectDialog {...defaultProps} />)

    expect(screen.getByRole('button', { name: /reject/i })).toBeEnabled()
  })

  it('remains enabled when note has content', async () => {
    const user = userEvent.setup()
    render(<BulkRejectDialog {...defaultProps} />)

    const noteField = screen.getByLabelText(/rejection note/i)
    await user.type(noteField, 'Test rejection reason')

    expect(screen.getByRole('button', { name: /reject/i })).toBeEnabled()
  })

  it('calls onConfirm with trimmed note when reject button clicked', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()

    render(<BulkRejectDialog {...defaultProps} onConfirm={onConfirm} />)

    const noteField = screen.getByLabelText(/rejection note/i)
    await user.type(noteField, '  Test rejection reason  ')

    await user.click(screen.getByRole('button', { name: /reject/i }))

    expect(onConfirm).toHaveBeenCalledWith('Test rejection reason')
  })

  it('calls onConfirm with null when note is empty', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()

    render(<BulkRejectDialog {...defaultProps} onConfirm={onConfirm} />)

    await user.click(screen.getByRole('button', { name: /reject/i }))

    expect(onConfirm).toHaveBeenCalledWith(null)
  })

  it('calls onClose when cancel button clicked', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()

    render(<BulkRejectDialog {...defaultProps} onClose={onClose} />)

    await user.click(screen.getByRole('button', { name: /cancel/i }))

    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('disables buttons when isLoading is true', async () => {
    const user = userEvent.setup()
    render(<BulkRejectDialog {...defaultProps} isLoading={true} />)

    const noteField = screen.getByLabelText(/rejection note/i)
    await user.type(noteField, 'Test reason')

    expect(screen.getByRole('button', { name: /reject/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeDisabled()
  })

  it('does not render when isOpen is false', () => {
    render(<BulkRejectDialog {...defaultProps} isOpen={false} />)

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('displays approval count in message', () => {
    render(<BulkRejectDialog {...defaultProps} />)

    expect(screen.getByText(/You are about to reject 2 approval steps/)).toBeInTheDocument()
  })

  it('displays singular form for single approval', () => {
    render(<BulkRejectDialog {...defaultProps} approvalCount={1} />)

    expect(screen.getByText(/You are about to reject 1 approval step\./)).toBeInTheDocument()
  })

  it('displays plural form for multiple approvals', () => {
    render(<BulkRejectDialog {...defaultProps} approvalCount={2} />)

    expect(screen.getByText(/You are about to reject 2 approval steps/)).toBeInTheDocument()
  })

  it('has warning icon in header', () => {
    render(<BulkRejectDialog {...defaultProps} />)

    const dialog = screen.getByRole('dialog')
    // PF6 titleIconVariant="warning" injects screen-reader text
    expect(within(dialog).getByText('Warning alert:')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<BulkRejectDialog {...defaultProps} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with note entered', async () => {
    const user = userEvent.setup()
    const { container } = render(<BulkRejectDialog {...defaultProps} />)

    const noteField = screen.getByLabelText(/rejection note/i)
    await user.type(noteField, 'Test rejection reason')

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

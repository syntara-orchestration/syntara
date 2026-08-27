import { render, screen } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { ApprovalsBulkActions } from './ApprovalsBulkActions'

describe('ApprovalsBulkActions', () => {
  const defaultProps = {
    selectedCount: 0,
    onApprove: vi.fn(),
    onReject: vi.fn(),
  }

  it('renders approve and reject buttons', () => {
    render(<ApprovalsBulkActions {...defaultProps} />)

    expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument()
  })

  it('disables buttons when no items selected', () => {
    render(<ApprovalsBulkActions {...defaultProps} selectedCount={0} />)

    expect(screen.getByRole('button', { name: /approve/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /reject/i })).toBeDisabled()
  })

  it('enables buttons when items are selected', () => {
    render(<ApprovalsBulkActions {...defaultProps} selectedCount={3} />)

    expect(screen.getByRole('button', { name: /approve/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /reject/i })).toBeEnabled()
  })

  it('shows selection count when items are selected', () => {
    render(<ApprovalsBulkActions {...defaultProps} selectedCount={5} />)

    expect(screen.getByText('5 selected')).toBeInTheDocument()
  })

  it('does not show selection count when no items selected', () => {
    render(<ApprovalsBulkActions {...defaultProps} selectedCount={0} />)

    expect(screen.queryByText(/selected/i)).not.toBeInTheDocument()
  })

  it('calls onApprove when approve button clicked', async () => {
    const user = userEvent.setup()
    const onApprove = vi.fn()

    render(<ApprovalsBulkActions {...defaultProps} selectedCount={2} onApprove={onApprove} />)

    await user.click(screen.getByRole('button', { name: /approve/i }))

    expect(onApprove).toHaveBeenCalledTimes(1)
  })

  it('calls onReject when reject button clicked', async () => {
    const user = userEvent.setup()
    const onReject = vi.fn()

    render(<ApprovalsBulkActions {...defaultProps} selectedCount={2} onReject={onReject} />)

    await user.click(screen.getByRole('button', { name: /reject/i }))

    expect(onReject).toHaveBeenCalledTimes(1)
  })

  it('disables buttons when isDisabled prop is true', () => {
    render(<ApprovalsBulkActions {...defaultProps} selectedCount={3} isDisabled={true} />)

    expect(screen.getByRole('button', { name: /approve/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /reject/i })).toBeDisabled()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ApprovalsBulkActions {...defaultProps} selectedCount={3} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('disables approve and reject when permission is denied via tooltip', () => {
    render(
      <ApprovalsBulkActions
        {...defaultProps}
        selectedCount={2}
        permissionTooltip="To approve or reject approvals, you need a role with the approval:decide policy."
      />
    )

    expect(screen.getByRole('button', { name: /approve/i })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('button', { name: /reject/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('has no accessibility violations when disabled', async () => {
    const { container } = render(<ApprovalsBulkActions {...defaultProps} selectedCount={0} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

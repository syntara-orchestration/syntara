import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { PublishWorkflowDialog } from './PublishWorkflowDialog'

const defaultProps = {
  isOpen: true,
  isPublishing: false,
  onClose: vi.fn(),
  onPublish: vi.fn(),
}

describe('PublishWorkflowDialog', () => {
  it('renders the dialog with title', () => {
    render(<PublishWorkflowDialog {...defaultProps} />)
    expect(screen.getByText('Publish workflow?')).toBeInTheDocument()
  })

  it('renders explanatory body text', () => {
    render(<PublishWorkflowDialog {...defaultProps} />)
    expect(screen.getByText(/This will override any previously published workflow/i)).toBeInTheDocument()
  })

  it('renders version name input with default date value', () => {
    render(<PublishWorkflowDialog {...defaultProps} />)
    const input = screen.getByLabelText('Version name')
    expect(input).toBeInTheDocument()
    expect(input).toHaveAttribute('value', expect.stringMatching(/\w+ \d+, \d{4}/))
  })

  it('renders description textarea', () => {
    render(<PublishWorkflowDialog {...defaultProps} />)
    expect(screen.getByLabelText('Description')).toBeInTheDocument()
  })

  it('description textarea accumulates typed characters', async () => {
    const user = userEvent.setup()
    render(<PublishWorkflowDialog {...defaultProps} />)

    const descInput = screen.getByLabelText('Description')
    await user.type(descInput, 'hello')

    expect(descInput).toHaveValue('hello')
  })

  it('calls onPublish with version name and description on submit', async () => {
    const user = userEvent.setup()
    const onPublish = vi.fn()
    render(<PublishWorkflowDialog {...defaultProps} onPublish={onPublish} />)

    const nameInput = screen.getByLabelText('Version name')
    await user.clear(nameInput)
    await user.type(nameInput, 'v1.0')
    await user.type(screen.getByLabelText('Description'), 'Initial release')
    await user.click(screen.getByRole('button', { name: 'Publish workflow' }))

    expect(onPublish).toHaveBeenCalledWith('v1.0', 'Initial release')
  })

  it('submits with default name when unchanged', async () => {
    const user = userEvent.setup()
    const onPublish = vi.fn()
    render(<PublishWorkflowDialog {...defaultProps} onPublish={onPublish} />)

    await user.click(screen.getByRole('button', { name: 'Publish workflow' }))

    expect(onPublish).toHaveBeenCalledWith(expect.stringMatching(/\w+ \d+, \d{4}/) as unknown, undefined)
  })

  it('calls onClose when cancel is clicked', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<PublishWorkflowDialog {...defaultProps} onClose={onClose} />)

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onClose).toHaveBeenCalled()
  })

  it('disables buttons when publishing', () => {
    render(<PublishWorkflowDialog {...defaultProps} isPublishing={true} />)

    expect(screen.getByRole('button', { name: /Publish/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  })

  it('does not render when closed', () => {
    render(<PublishWorkflowDialog {...defaultProps} isOpen={false} />)
    expect(screen.queryByText('Publish workflow?')).not.toBeInTheDocument()
  })

  it('shows validation error when version name is cleared', async () => {
    const user = userEvent.setup()
    render(<PublishWorkflowDialog {...defaultProps} />)

    const nameInput = screen.getByLabelText('Version name')
    await user.clear(nameInput)
    await user.click(screen.getByRole('button', { name: 'Publish workflow' }))

    expect(defaultProps.onPublish).not.toHaveBeenCalled()
    expect(screen.getByText('Version name is required')).toBeInTheDocument()
  })

  it('shows validation error when description exceeds 1000 characters', async () => {
    const user = userEvent.setup()
    render(<PublishWorkflowDialog {...defaultProps} />)

    const descInput = screen.getByLabelText('Description')
    await user.click(descInput)
    await user.paste('x'.repeat(1001))
    await user.click(screen.getByRole('button', { name: 'Publish workflow' }))

    expect(defaultProps.onPublish).not.toHaveBeenCalled()
    expect(screen.getByText('Description must be 1000 characters or fewer')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<PublishWorkflowDialog {...defaultProps} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

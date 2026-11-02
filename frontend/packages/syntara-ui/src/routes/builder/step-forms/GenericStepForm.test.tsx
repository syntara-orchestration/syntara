import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { GenericStepForm } from './GenericStepForm'

describe('GenericStepForm', () => {
  const mockOnSubmit = vi.fn()
  const mockOnCancel = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders description text and both buttons', () => {
    render(<GenericStepForm onSubmit={mockOnSubmit} onCancel={mockOnCancel} />)

    expect(screen.getByText(/generic placeholder step/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /add generic step/i })).toBeInTheDocument()
  })

  it('uses custom submitButtonText when provided', () => {
    render(<GenericStepForm onSubmit={mockOnSubmit} onCancel={mockOnCancel} submitButtonText="Add step" />)

    expect(screen.getByRole('button', { name: 'Add step' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /add generic step/i })).not.toBeInTheDocument()
  })

  it('calls onSubmit with empty object when primary button is clicked', async () => {
    const user = userEvent.setup()
    render(<GenericStepForm onSubmit={mockOnSubmit} onCancel={mockOnCancel} />)

    await user.click(screen.getByRole('button', { name: /add generic step/i }))

    expect(mockOnSubmit).toHaveBeenCalledWith({})
    expect(mockOnSubmit).toHaveBeenCalledTimes(1)
  })

  it('calls onCancel when cancel button is clicked', async () => {
    const user = userEvent.setup()
    render(<GenericStepForm onSubmit={mockOnSubmit} onCancel={mockOnCancel} />)

    await user.click(screen.getByRole('button', { name: /cancel/i }))

    expect(mockOnCancel).toHaveBeenCalledTimes(1)
    expect(mockOnSubmit).not.toHaveBeenCalled()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<GenericStepForm onSubmit={mockOnSubmit} onCancel={mockOnCancel} />)

    expect(await axe(container)).toHaveNoViolations()
  })
})

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AAPErrorAlert } from './AAPErrorAlert'

describe('AAPErrorAlert', () => {
  it('renders nothing when error is null', () => {
    const { container } = render(<AAPErrorAlert error={null} onRetry={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders error alert with message', () => {
    const error = new Error('Failed to connect to AAP')
    render(<AAPErrorAlert error={error} onRetry={vi.fn()} />)

    expect(screen.getByText('Failed to load AAP resources')).toBeInTheDocument()
    expect(screen.getByText('Failed to connect to AAP')).toBeInTheDocument()
  })

  it('shows retry button for retryable errors', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    const networkError = Object.assign(new Error('Network error'), { retryable: true })

    render(<AAPErrorAlert error={networkError} onRetry={onRetry} />)

    const retryButton = screen.getByRole('button', { name: /retry/i })
    expect(retryButton).toBeInTheDocument()

    await user.click(retryButton)
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('shows retry button for errors with retryable in data', () => {
    const retryableError = Object.assign(new Error('Request failed'), { data: { retryable: true } })

    render(<AAPErrorAlert error={retryableError} onRetry={vi.fn()} />)

    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })

  it('does not show retry button for non-retryable errors', () => {
    const validationError = new Error('Invalid credentials')
    validationError.name = 'ValidationError'

    render(<AAPErrorAlert error={validationError} onRetry={vi.fn()} />)

    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument()
  })

  it('has no accessibility violations with retry button', async () => {
    const retryableError = Object.assign(new Error('Failed to load'), { retryable: true })

    const { container } = render(<AAPErrorAlert error={retryableError} onRetry={vi.fn()} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations without retry button', async () => {
    const error = new Error('Validation failed')

    const { container } = render(<AAPErrorAlert error={error} onRetry={vi.fn()} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('displays custom error messages from Error objects', () => {
    const customError = new Error('Connection timeout after 30 seconds')
    render(<AAPErrorAlert error={customError} onRetry={vi.fn()} />)

    expect(screen.getByText('Failed to load AAP resources')).toBeInTheDocument()
    expect(screen.getByText('Connection timeout after 30 seconds')).toBeInTheDocument()
  })

  it('shows error message for non-retryable validation errors', () => {
    const validationError = new Error('Invalid template configuration')
    validationError.name = 'ValidationError'

    render(<AAPErrorAlert error={validationError} onRetry={vi.fn()} />)

    expect(screen.getByText('Failed to load AAP resources')).toBeInTheDocument()
    expect(screen.getByText('Invalid template configuration')).toBeInTheDocument()
    // Should not show retry button for validation errors
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument()
  })
})

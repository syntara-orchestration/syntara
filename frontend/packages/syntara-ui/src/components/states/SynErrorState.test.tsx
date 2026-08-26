import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SynErrorState } from './SynErrorState'

// Mock the apiErrors utilities
vi.mock('../../utils/apiErrors', () => ({
  getErrorMessage: (error: unknown) => {
    if (typeof error === 'string') return error
    if (error && typeof error === 'object' && 'message' in error) return (error as { message: string }).message
    return 'Unknown error'
  },
  getErrorTitle: (error: unknown) => {
    if (error && typeof error === 'object' && 'title' in error) return (error as { title: string }).title
    return 'Error'
  },
  isRetryableError: (error: unknown) => {
    if (error && typeof error === 'object' && 'retryable' in error) return (error as { retryable: boolean }).retryable
    return false
  },
  isServiceUnavailableError: (error: unknown) => {
    if (error && typeof error === 'object' && 'status' in error) return (error as { status: number }).status === 503
    return false
  },
}))

describe('SynErrorState', () => {
  it('has no accessibility violations', async () => {
    const { container } = render(<SynErrorState message="Something went wrong" />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with retry button', async () => {
    const error = { message: 'Retryable error', retryable: true }
    const { container } = render(<SynErrorState message={error} onRetry={vi.fn()} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders with error message string', () => {
    render(<SynErrorState message="Something went wrong" />)

    expect(screen.getByTestId('error-state')).toBeInTheDocument()
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
  })

  it('renders with custom title', () => {
    render(<SynErrorState title="Custom Error Title" message="Error details" />)

    expect(screen.getByText('Custom Error Title')).toBeInTheDocument()
    expect(screen.getByText('Error details')).toBeInTheDocument()
  })

  it('renders with error object', () => {
    const error = { message: 'API failed', title: 'API Error' }
    render(<SynErrorState message={error} />)

    expect(screen.getByText('API Error')).toBeInTheDocument()
    expect(screen.getByText('API failed')).toBeInTheDocument()
  })

  it('does not show retry button for non-retryable errors', () => {
    const onRetry = vi.fn()
    render(<SynErrorState message="Non-retryable error" onRetry={onRetry} />)

    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
  })

  it('shows retry button for retryable errors when onRetry provided', () => {
    const onRetry = vi.fn()
    const error = { message: 'Retryable error', retryable: true }
    render(<SynErrorState message={error} onRetry={onRetry} />)

    const retryButton = screen.getByRole('button', { name: 'Retry' })
    expect(retryButton).toBeInTheDocument()
  })

  it('calls onRetry when retry button is clicked', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    const error = { message: 'Retryable error', retryable: true }
    render(<SynErrorState message={error} onRetry={onRetry} />)

    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('renders EmptyStateServiceUnavailable for 503 errors', () => {
    const error = { message: 'Service unavailable', status: 503 }
    render(<SynErrorState message={error} />)

    // Should render EmptyStateServiceUnavailable instead
    expect(screen.getByText('Service Unavailable')).toBeInTheDocument()
  })

  it('does not show retry button when onRetry is not provided', () => {
    const error = { message: 'Retryable error', retryable: true }
    render(<SynErrorState message={error} />)

    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
  })
})

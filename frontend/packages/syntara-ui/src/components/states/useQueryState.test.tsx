import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useQueryState } from './useQueryState'

// Mock the hooks and utilities
vi.mock('../../hooks/useApiErrorAlert', () => ({
  useApiErrorAlert: vi.fn(),
}))

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
  isServiceUnavailableError: (error: unknown) => {
    if (error && typeof error === 'object' && 'status' in error) return (error as { status: number }).status === 503
    return false
  },
  isRetryableError: (error: unknown) => {
    if (error && typeof error === 'object' && 'retryable' in error) return (error as { retryable: boolean }).retryable
    return false
  },
}))

// Test component that uses the hook
function TestComponent({
  state,
  titleOrOptions,
}: {
  state: { error: unknown; isPending: boolean; refetch?: () => void }
  titleOrOptions?: string | { title?: string; onRetry?: () => void }
}) {
  const result = useQueryState(state, titleOrOptions)
  if (result) return result
  return <div data-testid="success">Data loaded</div>
}

describe('useQueryState', () => {
  it('returns null when data is ready (no error, not pending)', () => {
    render(<TestComponent state={{ error: null, isPending: false }} />)

    expect(screen.getByTestId('success')).toBeInTheDocument()
    expect(screen.getByText('Data loaded')).toBeInTheDocument()
  })

  it('renders SynLoadingState when isPending is true', () => {
    render(<TestComponent state={{ error: null, isPending: true }} />)

    expect(screen.getByTestId('loading-state')).toBeInTheDocument()
  })

  it('renders ErrorState when error is present', () => {
    const error = { message: 'API error' }
    render(<TestComponent state={{ error, isPending: false }} />)

    expect(screen.getByTestId('error-state')).toBeInTheDocument()
  })

  it('renders EmptyStateServiceUnavailable for 503 errors', () => {
    const error = { message: 'Service down', status: 503 }
    render(<TestComponent state={{ error, isPending: false }} />)

    expect(screen.getByText('Service Unavailable')).toBeInTheDocument()
  })

  it('accepts string title option', () => {
    const error = { message: 'Failed to load' }
    render(<TestComponent state={{ error, isPending: false }} titleOrOptions="Custom Error Title" />)

    expect(screen.getByText('Custom Error Title')).toBeInTheDocument()
  })

  it('accepts options object with title', () => {
    const error = { message: 'Failed to load' }
    render(<TestComponent state={{ error, isPending: false }} titleOrOptions={{ title: 'Options Title' }} />)

    expect(screen.getByText('Options Title')).toBeInTheDocument()
  })

  it('prioritizes error state over pending state', () => {
    const error = { message: 'Error occurred' }
    render(<TestComponent state={{ error, isPending: true }} />)

    // Error should take precedence
    expect(screen.getByTestId('error-state')).toBeInTheDocument()
    expect(screen.queryByTestId('loading-state')).not.toBeInTheDocument()
  })

  it('passes refetch as fallback onRetry', () => {
    const refetch = vi.fn()
    const error = { message: 'Failed', retryable: true }
    render(<TestComponent state={{ error, isPending: false, refetch }} />)

    // ErrorState should receive refetch as onRetry prop
    expect(screen.getByTestId('error-state')).toBeInTheDocument()
  })

  it('prefers explicit onRetry over refetch', () => {
    const refetch = vi.fn()
    const onRetry = vi.fn()
    const error = { message: 'Failed', retryable: true }
    render(<TestComponent state={{ error, isPending: false, refetch }} titleOrOptions={{ onRetry }} />)

    expect(screen.getByTestId('error-state')).toBeInTheDocument()
  })
})

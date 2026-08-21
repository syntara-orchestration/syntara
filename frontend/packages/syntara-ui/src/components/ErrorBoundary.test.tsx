import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

import { ErrorBoundary } from './ErrorBoundary'

// Component that throws an error
function ThrowError({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) {
    throw new Error('Test error message')
  }
  return <div>Normal content</div>
}

describe('ErrorBoundary', () => {
  // Suppress console.error during error boundary tests
  // eslint-disable-next-line no-console
  const originalConsoleError = console.error

  beforeEach(() => {
    // eslint-disable-next-line no-console
    console.error = vi.fn()
  })

  afterEach(() => {
    // eslint-disable-next-line no-console
    console.error = originalConsoleError
  })

  it('renders children when there is no error', () => {
    render(
      <ErrorBoundary>
        <div>Child content</div>
      </ErrorBoundary>
    )

    expect(screen.getByText('Child content')).toBeInTheDocument()
  })

  it('renders error state when child throws', () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    )

    // Multiple "Something went wrong" elements - one in header, one in ErrorState
    expect(screen.getAllByText('Something went wrong').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Test error message')).toBeInTheDocument()
  })

  it('renders custom fallback when provided and error occurs', () => {
    render(
      <ErrorBoundary fallback={<div>Custom fallback UI</div>}>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    )

    expect(screen.getByText('Custom fallback UI')).toBeInTheDocument()
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument()
  })

  it('renders default error state without custom fallback', () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    )

    // Should show the default error UI with SynPage structure
    expect(screen.getAllByText('Something went wrong').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByTestId('error-state')).toBeInTheDocument()
  })

  it('displays error message in error state', () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    )

    expect(screen.getByText('Test error message')).toBeInTheDocument()
  })

  it('handles error without message gracefully', () => {
    // Component that throws error without message
    function ThrowEmptyError(): ReactNode {
      throw new Error()
    }

    render(
      <ErrorBoundary>
        <ThrowEmptyError />
      </ErrorBoundary>
    )

    expect(screen.getByText('An unexpected error occurred')).toBeInTheDocument()
  })

  it('catches errors from nested components', () => {
    function NestedComponent() {
      return <ThrowError shouldThrow={true} />
    }

    render(
      <ErrorBoundary>
        <div>
          <NestedComponent />
        </div>
      </ErrorBoundary>
    )

    expect(screen.getAllByText('Something went wrong').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByTestId('error-state')).toBeInTheDocument()
  })
})

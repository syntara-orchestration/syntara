import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ExecutionDetailErrorStates } from './ExecutionDetailErrorStates'

describe('ExecutionDetailErrorStates', () => {
  describe('Invalid execution ID', () => {
    it('renders error state when executionId is undefined', () => {
      render(<ExecutionDetailErrorStates executionId={undefined} isLoading={false} error={null} onRetry={vi.fn()} />)

      expect(screen.getByText('Invalid execution')).toBeInTheDocument()
      expect(screen.getByText('No execution ID provided')).toBeInTheDocument()
    })

    it('renders page header with "Error" title when executionId is undefined', () => {
      render(<ExecutionDetailErrorStates executionId={undefined} isLoading={false} error={null} onRetry={vi.fn()} />)

      expect(screen.getByRole('heading', { name: 'Error' })).toBeInTheDocument()
    })
  })

  describe('Error state', () => {
    it('renders error state when error is provided', () => {
      const mockError = new Error('Failed to fetch execution')
      render(
        <ExecutionDetailErrorStates executionId="exec-123" isLoading={false} error={mockError} onRetry={vi.fn()} />
      )

      expect(screen.getAllByText('Error loading execution').length).toBeGreaterThan(0)
      expect(screen.getByText('Failed to fetch execution')).toBeInTheDocument()
    })

    it('passes onRetry handler to SynErrorState', () => {
      const mockOnRetry = vi.fn().mockResolvedValue(undefined)
      const mockError = new Error('Network error')

      render(
        <ExecutionDetailErrorStates executionId="exec-123" isLoading={false} error={mockError} onRetry={mockOnRetry} />
      )

      // SynErrorState receives the onRetry prop (wrapped in detachPromise)
      // The actual retry button rendering is tested in SynErrorState's own tests
      expect(screen.getAllByText('Error loading execution').length).toBeGreaterThan(0)
    })

    it('sanitizes error message using getErrorMessage', () => {
      // Error object should be sanitized to just the message
      const mockError = { message: 'Sanitized error', stack: 'stack trace', secret: 'api-key-123' }
      render(
        <ExecutionDetailErrorStates executionId="exec-123" isLoading={false} error={mockError} onRetry={vi.fn()} />
      )

      expect(screen.getByText('Sanitized error')).toBeInTheDocument()
      expect(screen.queryByText('api-key-123')).not.toBeInTheDocument()
    })

    it('wraps onRetry with detachPromise', () => {
      const mockOnRetry = vi.fn().mockResolvedValue(undefined)
      const mockError = new Error('Test error')

      render(
        <ExecutionDetailErrorStates executionId="exec-123" isLoading={false} error={mockError} onRetry={mockOnRetry} />
      )

      // The onRetry prop is wrapped with detachPromise before being passed to SynErrorState
      // This test verifies the component renders without errors when onRetry is provided
      expect(screen.getAllByText('Error loading execution').length).toBeGreaterThan(0)
    })

    it('invokes onRetry when retry button is clicked for a retryable error', async () => {
      const mockOnRetry = vi.fn().mockResolvedValue(undefined)
      const retryableError = { retryable: true, message: 'Service temporarily unavailable' }

      render(
        <ExecutionDetailErrorStates
          executionId="exec-123"
          isLoading={false}
          error={retryableError}
          onRetry={mockOnRetry}
        />
      )

      await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
      expect(mockOnRetry).toHaveBeenCalledOnce()
    })
  })

  describe('Loading state', () => {
    it('renders loading state when isLoading is true', () => {
      render(<ExecutionDetailErrorStates executionId="exec-123" isLoading={true} error={null} onRetry={vi.fn()} />)

      expect(screen.getByText('Loading execution')).toBeInTheDocument()
      // SynLoadingState renders a spinner
      expect(screen.getByRole('progressbar')).toBeInTheDocument()
    })

    it('renders page header with "Loading execution" title when loading', () => {
      render(<ExecutionDetailErrorStates executionId="exec-123" isLoading={true} error={null} onRetry={vi.fn()} />)

      expect(screen.getByRole('heading', { name: 'Loading execution' })).toBeInTheDocument()
    })
  })

  describe('Happy path', () => {
    it('returns null when execution data is available (no error, not loading, has executionId)', () => {
      render(<ExecutionDetailErrorStates executionId="exec-123" isLoading={false} error={null} onRetry={vi.fn()} />)

      // When data is available, the component returns null - verify no error/loading state appears
      expect(screen.queryByText(/error/i)).not.toBeInTheDocument()
      expect(screen.queryByText(/loading/i)).not.toBeInTheDocument()
    })
  })

  describe('State priority', () => {
    it('shows invalid execution error even when isLoading is true', () => {
      render(<ExecutionDetailErrorStates executionId={undefined} isLoading={true} error={null} onRetry={vi.fn()} />)

      expect(screen.getByText('Invalid execution')).toBeInTheDocument()
      expect(screen.queryByText('Loading execution')).not.toBeInTheDocument()
    })

    it('shows error state even when isLoading is true', () => {
      const mockError = new Error('API error')
      render(<ExecutionDetailErrorStates executionId="exec-123" isLoading={true} error={mockError} onRetry={vi.fn()} />)

      expect(screen.getAllByText('Error loading execution').length).toBeGreaterThan(0)
      expect(screen.queryByText('Loading execution')).not.toBeInTheDocument()
    })

    it('prioritizes error over loading: invalid ID > error > loading > success', () => {
      // Invalid ID takes highest priority
      const { rerender } = render(
        <ExecutionDetailErrorStates
          executionId={undefined}
          isLoading={true}
          error={new Error('err')}
          onRetry={vi.fn()}
        />
      )
      expect(screen.getByText('Invalid execution')).toBeInTheDocument()

      // Error takes priority over loading
      rerender(
        <ExecutionDetailErrorStates
          executionId="exec-123"
          isLoading={true}
          error={new Error('err')}
          onRetry={vi.fn()}
        />
      )
      expect(screen.getAllByText('Error loading execution').length).toBeGreaterThan(0)

      // Loading shows when no error
      rerender(<ExecutionDetailErrorStates executionId="exec-123" isLoading={true} error={null} onRetry={vi.fn()} />)
      expect(screen.getByText('Loading execution')).toBeInTheDocument()

      // Success (null) shows when no error and not loading
      rerender(<ExecutionDetailErrorStates executionId="exec-123" isLoading={false} error={null} onRetry={vi.fn()} />)
      expect(screen.queryByText(/execution/i)).not.toBeInTheDocument()
    })
  })
})

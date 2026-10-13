import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'

import type { RetryFromFailurePreview } from './retryFromFailure'
import { RetryFromFailureDialog } from './RetryFromFailureDialog'

function preview(overrides: Partial<RetryFromFailurePreview> = {}): RetryFromFailurePreview {
  return {
    eligible: true,
    eligible_point_ids: ['node-a'],
    total_step_count: 3,
    ...overrides,
  }
}

function renderDialog(props: Partial<React.ComponentProps<typeof RetryFromFailureDialog>> = {}) {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    onConfirm: vi.fn(),
    preview: preview(),
    isPreviewLoading: false,
    isPreviewError: false,
    ...props,
  }
  return { ...render(<RetryFromFailureDialog {...defaultProps} />), props: defaultProps }
}

describe('RetryFromFailureDialog', () => {
  it('summarizes the retry scope without listing steps individually', () => {
    renderDialog({ preview: preview({ eligible_point_ids: ['a', 'b'], total_step_count: 5 }) })

    expect(screen.getByText('Retry from failure?')).toBeInTheDocument()
    expect(
      screen.getByText('Retrying will resume at 2 failure points and re-run 5 steps. Steps that already completed keep their output.')
    ).toBeInTheDocument()
  })

  it('surfaces the backend rejection reason and blocks confirming', () => {
    renderDialog({ preview: preview({ eligible: false, reason: 'Execution is still running.', eligible_point_ids: [] }) })

    expect(screen.getByTestId('retry-rejected')).toBeInTheDocument()
    expect(screen.getByText('Execution is still running.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry from failure' })).toBeDisabled()
  })

  it('shows a loading state while the preview is in flight', () => {
    renderDialog({ isPreviewLoading: true, preview: undefined })

    expect(screen.getByLabelText('Checking retry options')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry from failure' })).toBeDisabled()
  })

  it('blocks confirming when the preview failed to load', () => {
    renderDialog({ isPreviewError: true, preview: undefined })

    expect(screen.getByTestId('retry-preview-error')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry from failure' })).toBeDisabled()
  })

  it('calls onConfirm when an eligible retry is confirmed', async () => {
    const user = userEvent.setup()
    const { props } = renderDialog()

    await user.click(screen.getByRole('button', { name: 'Retry from failure' }))

    expect(props.onConfirm).toHaveBeenCalledOnce()
  })

  it('calls onClose when the dialog is cancelled', async () => {
    const user = userEvent.setup()
    const { props } = renderDialog()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(props.onClose).toHaveBeenCalledOnce()
  })

  it('does not render when closed', () => {
    renderDialog({ isOpen: false })

    expect(screen.queryByText('Retry from failure?')).not.toBeInTheDocument()
  })

  it('has no accessibility violations when eligible', async () => {
    const { container } = renderDialog()
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when rejected', async () => {
    const { container } = renderDialog({ preview: preview({ eligible: false, reason: 'Nope.', eligible_point_ids: [] }) })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
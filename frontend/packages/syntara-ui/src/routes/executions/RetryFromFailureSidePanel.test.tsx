import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'

import { routerTestState } from '../../test/setup'

import { useRetryFromFailure } from './hooks/useRetryFromFailure'
import { useRetryFromFailurePreview } from './hooks/useRetryFromFailurePreview'
import { RetryFromFailureSidePanel } from './RetryFromFailureSidePanel'

const mockHandleRetry = vi.fn()

vi.mock('./hooks/useRetryFromFailure', () => ({
  useRetryFromFailure: vi.fn(() => ({ handleRetry: mockHandleRetry, isPending: false })),
}))

vi.mock('./hooks/useRetryFromFailurePreview', () => ({
  useRetryFromFailurePreview: vi.fn(() => ({
    preview: {
      eligible: true,
      eligible_point_ids: ['step-2'],
      step_count_by_eligible_point: { 'step-2': 3 },
      total_step_count: 3,
    },
    isLoading: false,
    isError: false,
  })),
}))

function renderPanel(props?: Partial<React.ComponentProps<typeof RetryFromFailureSidePanel>>) {
  const defaultProps = {
    executionId: 'exec-123',
    activityNameMap: new Map([
      ['step-1', 'First Step'],
      ['step-2', 'Second Step'],
    ]),
    onClose: vi.fn(),
    ...props,
  }
  return { ...render(<RetryFromFailureSidePanel {...defaultProps} />), props: defaultProps }
}

describe('RetryFromFailureSidePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useRetryFromFailure).mockReturnValue({ handleRetry: mockHandleRetry, isPending: false })
    vi.mocked(useRetryFromFailurePreview).mockReturnValue({
      preview: {
        eligible: true,
        eligible_point_ids: ['step-2'],
        step_count_by_eligible_point: { 'step-2': 3 },
        total_step_count: 3,
      },
      isLoading: false,
      isError: false,
    })
    routerTestState.navigate.mockClear()
  })

  it('shows retry guidance and the backend-provided plan', () => {
    renderPanel()

    expect(screen.getByRole('complementary', { name: 'Retry from failure review' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'How retry works' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Retry plan' })).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('Second Step')).toBeInTheDocument()
    expect(screen.getByText('3 steps in this retry path')).toBeInTheDocument()
    expect(screen.getByTestId('retry-retained-results-copy')).toHaveTextContent(
      'Completed results outside these retry paths keep their original output.'
    )
  })

  it('narrows the plan and request to the selected failed node', async () => {
    const user = userEvent.setup()
    vi.mocked(useRetryFromFailurePreview).mockReturnValue({
      preview: {
        eligible: true,
        eligible_point_ids: ['step-1', 'step-2'],
        step_count_by_eligible_point: { 'step-1': 4, 'step-2': 3 },
        total_step_count: 5,
      },
      isLoading: false,
      isError: false,
    })
    renderPanel({ selectedNodeId: 'step-2' })

    expect(screen.getByText('Second Step')).toBeInTheDocument()
    expect(screen.queryByText('First Step')).not.toBeInTheDocument()
    await user.click(screen.getByTestId('retry-from-failure-confirm'))

    expect(mockHandleRetry).toHaveBeenCalledWith(['step-2'])
  })

  it('shows a loading state and disables retry while the plan loads', () => {
    vi.mocked(useRetryFromFailurePreview).mockReturnValue({ preview: undefined, isLoading: true, isError: false })
    renderPanel()

    expect(screen.getByLabelText('Loading retry plan')).toBeInTheDocument()
    expect(screen.getByTestId('retry-from-failure-confirm')).toBeDisabled()
  })

  it('shows a retryable preview error and disables retry', () => {
    vi.mocked(useRetryFromFailurePreview).mockReturnValue({ preview: undefined, isLoading: false, isError: true })
    renderPanel()

    expect(screen.getByRole('heading', { name: 'Danger alert: Could not load retry plan' })).toBeInTheDocument()
    expect(screen.getByTestId('retry-from-failure-confirm')).toBeDisabled()
  })

  it('shows the backend rejection reason and disables retry', () => {
    vi.mocked(useRetryFromFailurePreview).mockReturnValue({
      preview: { eligible: false, reason: 'This execution is still running.', eligible_point_ids: [] },
      isLoading: false,
      isError: false,
    })
    renderPanel()

    expect(
      screen.getByRole('heading', { name: 'Warning alert: This run cannot be retried from failure' })
    ).toBeInTheDocument()
    expect(screen.getByText('This execution is still running.')).toBeInTheDocument()
    expect(screen.getByTestId('retry-from-failure-confirm')).toBeDisabled()
  })

  it('shows a fallback message when the backend does not include a rejection reason', () => {
    vi.mocked(useRetryFromFailurePreview).mockReturnValue({
      preview: { eligible: false, eligible_point_ids: [] },
      isLoading: false,
      isError: false,
    })
    renderPanel()

    expect(
      screen.getByRole('heading', { name: 'Warning alert: This run cannot be retried from failure' })
    ).toBeInTheDocument()
    expect(screen.getByText('No failed steps were found to retry from.')).toBeInTheDocument()
  })

  it('shows an empty state when an eligible preview contains no retry points', () => {
    vi.mocked(useRetryFromFailurePreview).mockReturnValue({
      preview: { eligible: true, eligible_point_ids: [], total_step_count: 0 },
      isLoading: false,
      isError: false,
    })
    renderPanel()

    expect(screen.getByRole('heading', { name: 'Warning alert: No retry points found' })).toBeInTheDocument()
    expect(screen.getByTestId('retry-from-failure-confirm')).toBeDisabled()
  })

  it('uses fallback labels when the preview omits retry path step counts', () => {
    vi.mocked(useRetryFromFailurePreview).mockReturnValue({
      preview: { eligible: true, eligible_point_ids: ['step-2'] },
      isLoading: false,
      isError: false,
    })
    renderPanel({ selectedNodeId: 'step-2' })

    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.getByText('Included in the retry plan')).toBeInTheDocument()
  })

  it('uses the singular step label for a one-step retry path', () => {
    vi.mocked(useRetryFromFailurePreview).mockReturnValue({
      preview: {
        eligible: true,
        eligible_point_ids: ['step-2'],
        step_count_by_eligible_point: { 'step-2': 1 },
        total_step_count: 1,
      },
      isLoading: false,
      isError: false,
    })
    renderPanel()

    expect(screen.getByText('1 step in this retry path')).toBeInTheDocument()
  })

  it('keeps the default plan when the selected node is auto-included', async () => {
    const user = userEvent.setup()
    vi.mocked(useRetryFromFailurePreview).mockReturnValue({
      preview: {
        eligible: true,
        eligible_point_ids: ['step-1', 'step-2'],
        auto_included_node_ids: ['step-2'],
        step_count_by_eligible_point: { 'step-1': 4, 'step-2': 3 },
        total_step_count: 5,
      },
      isLoading: false,
      isError: false,
    })
    renderPanel({ selectedNodeId: 'step-2' })

    expect(screen.getByText('First Step')).toBeInTheDocument()
    expect(screen.getByText('Second Step')).toBeInTheDocument()
    await user.click(screen.getByTestId('retry-from-failure-confirm'))

    expect(mockHandleRetry).toHaveBeenCalledWith(undefined)
  })

  it('disables retry and cancel while the retry request is pending', () => {
    vi.mocked(useRetryFromFailure).mockReturnValue({ handleRetry: mockHandleRetry, isPending: true })
    renderPanel()

    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    expect(screen.getByTestId('retry-from-failure-confirm')).toBeDisabled()
  })

  it('calls retry, closes the panel, and navigates to the new execution on success', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    vi.mocked(useRetryFromFailure).mockImplementation(({ onSuccess }) => {
      mockHandleRetry.mockImplementation(() => onSuccess?.('new-exec-id'))
      return { handleRetry: mockHandleRetry, isPending: false }
    })
    renderPanel({ onClose })

    await user.click(screen.getByTestId('retry-from-failure-confirm'))

    expect(mockHandleRetry).toHaveBeenCalledOnce()
    expect(onClose).toHaveBeenCalledOnce()
    expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/executions/new-exec-id' })
  })

  it('closes the panel from its header and cancel action', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    renderPanel({ onClose })

    await user.click(screen.getByRole('button', { name: 'Close retry review' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('has no accessibility violations in the loaded state', async () => {
    const { container } = renderPanel()
    const results = await axe(container)

    expect(results).toHaveNoViolations()
  })
})

import { render, screen, waitFor } from '@testing-library/react'
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
      retained_result_count: 1,
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
    activityTypeMap: new Map([
      ['step-1', 'script'],
      ['step-2', 'script'],
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
        retained_result_count: 1,
      },
      isLoading: false,
      isError: false,
    })
    routerTestState.navigate.mockClear()
  })

  it('shows retry guidance and the backend-provided plan', () => {
    renderPanel()

    expect(screen.getByRole('complementary', { name: 'Retry run from failure review' })).toBeInTheDocument()
    expect(screen.getByTestId('retry-from-failure-panel')).toHaveFocus()
    expect(screen.getByRole('heading', { name: 'How retry works' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Retry plan' })).toBeInTheDocument()
    expect(screen.getByText('3 steps will be retried')).toBeInTheDocument()
    expect(screen.getByText('Includes affected steps and any downstream merge step')).toBeInTheDocument()
    expect(screen.getByText('Second Step')).toBeInTheDocument()
    expect(screen.getByText('Script')).toBeInTheDocument()
    expect(screen.getByText('1 completed result retained')).toBeInTheDocument()
    expect(
      screen.getByText(/This retry uses the same workflow version as this run, preserving the definition that ran/)
    ).toBeInTheDocument()
    expect(screen.getByText(/Nodes outside the selected retry scope will not re-execute/)).toBeInTheDocument()
    expect(
      screen.getByText(/Completed nodes retain their previous result, failed nodes remain failed/)
    ).toBeInTheDocument()
    expect(screen.getByText(/nodes that did not run remain skipped/)).toBeInTheDocument()
    expect(screen.getByText(/may repeat external side effects/)).toBeInTheDocument()
    expect(
      screen.getByText(/To change the parameters for this retry, select the failed node in Run details/)
    ).toBeInTheDocument()
  })

  it('defaults the retry scope to all affected branches', async () => {
    const user = userEvent.setup()
    vi.mocked(useRetryFromFailurePreview).mockReturnValue({
      preview: {
        eligible: true,
        eligible_point_ids: ['step-1', 'step-2'],
        step_count_by_eligible_point: { 'step-1': 4, 'step-2': 3 },
        total_step_count: 5,
        retained_result_count: 2,
      },
      isLoading: false,
      isError: false,
    })
    vi.mocked(useRetryFromFailurePreview).mockImplementation(({ retryPointIds }) => {
      const selectedIds = retryPointIds ?? ['step-1', 'step-2']
      return {
        preview: {
          eligible: true,
          eligible_point_ids: selectedIds,
          step_count_by_eligible_point: { 'step-1': 4, 'step-2': 3 },
          total_step_count: selectedIds.length === 1 ? 3 : 5,
          retained_result_count: 2,
        },
        isLoading: false,
        isError: false,
      }
    })
    renderPanel()

    expect(screen.getByRole('radio', { name: 'Retry all affected branches' })).toBeChecked()
    expect(screen.getByText('5 steps will be retried')).toBeInTheDocument()
    await user.click(screen.getByTestId('retry-from-failure-confirm'))

    expect(mockHandleRetry).toHaveBeenCalledWith(undefined, {})
  })

  it('submits saved input overrides with the retry request', async () => {
    const user = userEvent.setup()
    const overrides = { 'step-2': { endpoint: 'https://retry.example' } }
    renderPanel({ inputParameterOverrides: overrides })

    await user.click(screen.getByTestId('retry-from-failure-confirm'))

    expect(mockHandleRetry).toHaveBeenCalledWith(undefined, overrides)
  })

  it('requires input edits to be saved or cancelled before retrying', () => {
    renderPanel({ hasUnsavedInputOverrides: true })

    expect(screen.getByText('Save or cancel input changes in Run details before retrying.')).toBeInTheDocument()
    expect(screen.getByTestId('retry-from-failure-confirm')).toBeDisabled()
  })

  it('previews an exact selected subset and retries only the checked branches', async () => {
    const user = userEvent.setup()
    const onRetryPreviewPointIdsChange = vi.fn()
    const allPoints = ['step-1', 'step-2']
    vi.mocked(useRetryFromFailurePreview).mockImplementation(({ retryPointIds }) => {
      const selectedIds = retryPointIds ?? allPoints
      const isBothSelected = selectedIds.length === 2
      let totalStepCount = 3
      if (isBothSelected) totalStepCount = 5
      else if (selectedIds[0] === 'step-1') totalStepCount = 4
      return {
        preview: {
          eligible: true,
          eligible_point_ids: selectedIds,
          step_count_by_eligible_point: { 'step-1': 4, 'step-2': 3 },
          total_step_count: totalStepCount,
          retained_result_count: isBothSelected ? 2 : 3,
        },
        isLoading: false,
        isError: false,
      }
    })
    renderPanel({ onRetryPreviewPointIdsChange })

    await waitFor(() => expect(onRetryPreviewPointIdsChange).toHaveBeenLastCalledWith(allPoints))

    await user.click(screen.getByRole('radio', { name: 'Choose branches' }))
    await waitFor(() => expect(onRetryPreviewPointIdsChange).toHaveBeenLastCalledWith([]))
    await user.click(screen.getByRole('checkbox', { name: 'First Step' }))
    await waitFor(() => expect(onRetryPreviewPointIdsChange).toHaveBeenLastCalledWith(['step-1']))

    expect(screen.getByText('4 steps will be retried')).toBeInTheDocument()
    expect(screen.getByText('3 completed results retained')).toBeInTheDocument()
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Retry plan updated. 1 selected branch. 4 steps to retry. Retry starts at First Step. 3 completed results retained.'
    )
    const retryStartsAt = screen.getByTestId('retry-starts-at')
    expect(retryStartsAt).toHaveTextContent('First Step')
    expect(retryStartsAt).not.toHaveTextContent('Second Step')

    await user.click(screen.getByRole('checkbox', { name: 'Second Step' }))
    await waitFor(() => expect(onRetryPreviewPointIdsChange).toHaveBeenLastCalledWith(allPoints))
    expect(screen.getByText('5 steps will be retried')).toBeInTheDocument()
    expect(screen.getByText('2 completed results retained')).toBeInTheDocument()
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Retry plan updated. 2 selected branches. 5 steps to retry. Retry starts at First Step, Second Step. 2 completed results retained.'
    )

    await user.click(screen.getByTestId('retry-from-failure-confirm'))
    expect(mockHandleRetry).toHaveBeenCalledWith(['step-1', 'step-2'], {})
  })

  it('requires a selected branch before showing a subset plan', async () => {
    const user = userEvent.setup()
    vi.mocked(useRetryFromFailurePreview).mockReturnValue({
      preview: {
        eligible: true,
        eligible_point_ids: ['step-1', 'step-2'],
        step_count_by_eligible_point: { 'step-1': 4, 'step-2': 3 },
        total_step_count: 5,
        retained_result_count: 2,
      },
      isLoading: false,
      isError: false,
    })
    renderPanel()

    await user.click(screen.getByRole('radio', { name: 'Choose branches' }))

    expect(screen.getByRole('heading', { name: 'Info alert: Choose at least one branch' })).toBeInTheDocument()
    expect(screen.getByTestId('retry-from-failure-confirm')).toBeDisabled()
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
    renderPanel()

    expect(screen.getByText('The number of steps to retry is unavailable.')).toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.getByText('Second Step')).toBeInTheDocument()
  })

  it('uses the singular step label for a one-step retry path', () => {
    vi.mocked(useRetryFromFailurePreview).mockReturnValue({
      preview: {
        eligible: true,
        eligible_point_ids: ['step-2'],
        step_count_by_eligible_point: { 'step-2': 1 },
        total_step_count: 1,
        retained_result_count: 0,
      },
      isLoading: false,
      isError: false,
    })
    renderPanel()

    expect(screen.getByText('1 step will be retried')).toBeInTheDocument()
  })

  it('keeps auto-included points in the all-points retry plan', async () => {
    const user = userEvent.setup()
    vi.mocked(useRetryFromFailurePreview).mockReturnValue({
      preview: {
        eligible: true,
        eligible_point_ids: ['step-1', 'step-2'],
        auto_included_node_ids: ['step-2'],
        sanitized_replacements: { 'step-failed': ['step-2'] },
        step_count_by_eligible_point: { 'step-1': 4, 'step-2': 3 },
        total_step_count: 5,
      },
      isLoading: false,
      isError: false,
    })
    renderPanel()

    expect(screen.getByTestId('retry-starts-at')).toHaveTextContent('First Step')
    expect(screen.getByTestId('retry-starts-at')).toHaveTextContent('Second Step')
    expect(screen.getByTestId('retry-unavailable-output')).toHaveTextContent('Second Step')
    expect(screen.getByRole('radio', { name: 'Retry all affected branches' })).toBeChecked()
    expect(screen.queryByRole('checkbox', { name: 'First Step' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('radio', { name: 'Choose branches' }))
    expect(screen.getByRole('checkbox', { name: 'First Step' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Second Step' })).toBeInTheDocument()
    await user.click(screen.getByRole('radio', { name: 'Retry all affected branches' }))
    await user.click(screen.getByTestId('retry-from-failure-confirm'))

    expect(mockHandleRetry).toHaveBeenCalledWith(undefined, {})
  })

  it('shows sanitized output in the retry plan and lets the replacement be selected', async () => {
    const user = userEvent.setup()
    vi.mocked(useRetryFromFailurePreview).mockImplementation(({ retryPointIds }) => {
      const selectedIds = retryPointIds ?? ['step-1', 'step-2']
      return {
        preview: {
          eligible: true,
          eligible_point_ids: selectedIds,
          auto_included_node_ids: retryPointIds ? [] : ['step-2'],
          sanitized_replacements: { 'step-failed': ['step-2'] },
          step_count_by_eligible_point: { 'step-1': 4, 'step-2': 3 },
          total_step_count: selectedIds.length === 1 ? 3 : 5,
          retained_result_count: 1,
        },
        isLoading: false,
        isError: false,
      }
    })
    const { container } = renderPanel()

    expect(screen.getByRole('heading', { name: 'Warning alert: Output sanitized' })).toBeInTheDocument()
    expect(screen.getByTestId('retry-sanitized-output-alert')).toHaveTextContent(
      'Output from Second Step was sanitized and cannot be reused. The retry will begin at Second Step to regenerate the missing input for step-failed.'
    )
    expect(screen.getByTestId('retry-unavailable-output')).toHaveTextContent('Second Step')
    expect(screen.getByTestId('retry-unavailable-output')).toHaveTextContent(
      'Sanitized for safety and regenerated during retry'
    )

    await user.click(screen.getByRole('radio', { name: 'Choose branches' }))
    await user.click(screen.getByRole('checkbox', { name: 'Second Step' }))

    expect(screen.getByTestId('retry-starts-at')).toHaveTextContent('Second Step')
    await user.click(screen.getByTestId('retry-from-failure-confirm'))
    expect(mockHandleRetry).toHaveBeenCalledWith(['step-2'], {})
    expect(await axe(container)).toHaveNoViolations()
  })

  it('describes sanitized replacement starts and warns when a failed branch is left unselected', async () => {
    const user = userEvent.setup()
    const allPoints = ['fetch-inventory', 'call-api']
    vi.mocked(useRetryFromFailurePreview).mockImplementation(({ retryPointIds }) => {
      const selectedIds = retryPointIds ?? allPoints
      return {
        preview: {
          eligible: true,
          eligible_point_ids: selectedIds,
          sanitized_replacements: { 'process-inventory': ['fetch-inventory'] },
          step_count_by_eligible_point: { 'fetch-inventory': 4, 'call-api': 3 },
          total_step_count: selectedIds.length === 1 ? 3 : 5,
          retained_result_count: 2,
        },
        isLoading: false,
        isError: false,
      }
    })
    const { container } = renderPanel({
      activityNameMap: new Map([
        ['fetch-inventory', 'Fetch inventory'],
        ['process-inventory', 'Process inventory'],
        ['call-api', 'Call external API'],
      ]),
      activityTypeMap: new Map([
        ['fetch-inventory', 'script'],
        ['call-api', 'script'],
      ]),
      workflowEdges: [
        { source: 'fetch-inventory', target: 'process-inventory' },
        { source: 'call-api', target: 'publish-results' },
      ],
      failedActivityIds: ['process-inventory', 'call-api'],
    })

    await user.click(screen.getByRole('radio', { name: 'Choose branches' }))
    expect(
      screen.getByRole('heading', { name: 'Select the branches where the retry should begin' })
    ).toBeInTheDocument()
    expect(screen.getByText('Failed node: Process inventory')).toBeInTheDocument()
    expect(screen.getByText('Output sanitized — retry starts upstream')).toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: 'Call external API' }))

    expect(screen.getByTestId('retry-partial-scope-warning')).toHaveTextContent('Some branches may fail')
    expect(screen.getByTestId('retry-plan-card')).toHaveTextContent('1 of 2 affected branches selected')
    expect(screen.getByTestId('retry-plan-card')).toHaveTextContent('1 failed step remains failed')
    expect(await axe(container)).toHaveNoViolations()
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

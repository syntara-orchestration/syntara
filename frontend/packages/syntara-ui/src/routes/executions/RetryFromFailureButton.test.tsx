import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'

import { useCanI } from '../../hooks/useCanI'
import { routerTestState } from '../../test/setup'

import { useRetryFromFailure } from './hooks/useRetryFromFailure'
import { useRetryFromFailurePreview } from './hooks/useRetryFromFailurePreview'
import { RetryFromFailureButton } from './RetryFromFailureButton'

const mockHandleRetry = vi.fn()

vi.mock('../../hooks/useCanI', () => ({
  useCanI: vi.fn(() => ({ allowed: true, isChecking: false, isError: false })),
}))

vi.mock('./hooks/useRetryFromFailure', () => ({
  useRetryFromFailure: vi.fn(() => ({ handleRetry: mockHandleRetry, isPending: false })),
}))

vi.mock('./hooks/useRetryFromFailurePreview', () => ({
  useRetryFromFailurePreview: vi.fn(() => ({ preview: undefined, isLoading: false, isError: false })),
}))

function renderButton(props?: Partial<React.ComponentProps<typeof RetryFromFailureButton>>) {
  const defaultProps = { executionId: 'exec-123', projectId: 'project-1', ...props }
  return render(<RetryFromFailureButton {...defaultProps} />)
}

describe('RetryFromFailureButton', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useCanI).mockReturnValue({ allowed: true, isChecking: false, isError: false })
    vi.mocked(useRetryFromFailure).mockReturnValue({ handleRetry: mockHandleRetry, isPending: false })
    vi.mocked(useRetryFromFailurePreview).mockReturnValue({ preview: undefined, isLoading: false, isError: false })
    routerTestState.navigate.mockClear()
  })

  it('renders an enabled retry-from-failure button', () => {
    renderButton()
    const button = screen.getByRole('button', { name: 'Retry from failure' })
    expect(button).toBeInTheDocument()
    expect(button).toBeEnabled()
  })

  it('opens the dialog on click', async () => {
    const user = userEvent.setup()
    renderButton()

    await user.click(screen.getByRole('button', { name: 'Retry from failure' }))

    expect(screen.getByText('Retry from failure?')).toBeInTheDocument()
  })

  it('only fetches the preview once the dialog is open', async () => {
    const user = userEvent.setup()
    renderButton()

    expect(useRetryFromFailurePreview).toHaveBeenLastCalledWith({ executionId: 'exec-123', enabled: false })

    await user.click(screen.getByRole('button', { name: 'Retry from failure' }))

    expect(useRetryFromFailurePreview).toHaveBeenLastCalledWith({ executionId: 'exec-123', enabled: true })
  })

  it('passes resourceProject to useCanI', () => {
    renderButton({ projectId: 'proj-42' })

    expect(useCanI).toHaveBeenCalledWith('run', 'execution', { resourceProject: 'proj-42' })
  })

  it('is aria-disabled when the user lacks execution:run permission', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })

    renderButton()

    const button = screen.getByRole('button', { name: 'Retry from failure' })
    expect(button).toHaveAttribute('aria-disabled', 'true')
  })

  it('is aria-disabled while the permission check is in flight', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: true, isError: false })

    renderButton()

    const button = screen.getByRole('button', { name: 'Retry from failure' })
    expect(button).toHaveAttribute('aria-disabled', 'true')
  })

  it('does not open the dialog when the button is disabled', async () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })
    const user = userEvent.setup()
    renderButton()

    await user.click(screen.getByRole('button', { name: 'Retry from failure' }))

    expect(screen.queryByText('Retry from failure?')).not.toBeInTheDocument()
  })

  it('navigates to the new execution and closes the dialog on a successful retry', async () => {
    vi.mocked(useRetryFromFailure).mockImplementation(({ onSuccess }) => {
      mockHandleRetry.mockImplementation(() => onSuccess?.('new-exec-id'))
      return { handleRetry: mockHandleRetry, isPending: false }
    })
    vi.mocked(useRetryFromFailurePreview).mockReturnValue({
      preview: { eligible: true, eligible_point_ids: ['step2'], total_step_count: 1 },
      isLoading: false,
      isError: false,
    })
    const user = userEvent.setup()
    renderButton()

    await user.click(screen.getByRole('button', { name: 'Retry from failure' }))
    expect(screen.getByText('Retry from failure?')).toBeInTheDocument()

    const confirmButtons = screen.getAllByRole('button', { name: 'Retry from failure' })
    await user.click(confirmButtons[confirmButtons.length - 1])

    expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/executions/new-exec-id' })
    expect(screen.queryByText('Retry from failure?')).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = renderButton()
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

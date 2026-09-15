import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'

import { executionsClient } from '../../client'
import { useCanI } from '../../hooks/useCanI'

import { RetryExecutionButton } from './RetryExecutionButton'

const mockMutate = vi.fn()
const mockShowSuccess = vi.fn()
const mockShowError = vi.fn()
const mockNavigate = vi.fn()

vi.mock('../../client', () => ({
  executionsClient: {
    useMutation: vi.fn(() => ({
      mutate: mockMutate,
      isPending: false,
    })),
  },
  workflowClient: {
    useQuery: vi.fn(() => ({ data: null, isLoading: false, error: null })),
  },
  authMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../hooks/useCanI', () => ({
  useCanI: vi.fn(() => ({ allowed: true, isChecking: false, isError: false })),
}))

vi.mock('../../hooks/routing/useNavigate', () => ({
  useNavigate: vi.fn(() => mockNavigate),
}))

vi.mock('../../providers/alerts/AlertContext', () => ({
  useAlerts: () => ({
    showSuccess: mockShowSuccess,
    showError: mockShowError,
  }),
}))

function renderButton(props?: Partial<React.ComponentProps<typeof RetryExecutionButton>>) {
  const queryClient = new QueryClient()
  const defaultProps = {
    executionId: 'exec-123',
    workflowId: 'wf-1',
    workflowVersionId: 'wfv-1',
    projectId: 'project-1',
    ...props,
  }
  return render(
    <QueryClientProvider client={queryClient}>
      <RetryExecutionButton {...defaultProps} />
    </QueryClientProvider>
  )
}

describe('RetryExecutionButton', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(executionsClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    } as never)
    vi.mocked(useCanI).mockReturnValue({ allowed: true, isChecking: false, isError: false })
  })

  it('renders an enabled retry button', () => {
    renderButton()
    const button = screen.getByRole('button', { name: 'Retry run' })
    expect(button).toBeInTheDocument()
    expect(button).toBeEnabled()
  })

  it('opens dialog on click', async () => {
    const user = userEvent.setup()
    renderButton()

    await user.click(screen.getByRole('button', { name: 'Retry run' }))

    expect(screen.getByText('Retry run?')).toBeInTheDocument()
  })

  it('calls mutate when dialog confirm is clicked', async () => {
    const user = userEvent.setup()
    renderButton()

    await user.click(screen.getByRole('button', { name: 'Retry run' }))

    const confirmButtons = screen.getAllByRole('button', { name: 'Retry run' })
    await user.click(confirmButtons[confirmButtons.length - 1])

    expect(mockMutate).toHaveBeenCalled()
  })

  it('passes resourceProject to useCanI when projectId is provided', () => {
    renderButton({ projectId: 'proj-42' })

    expect(useCanI).toHaveBeenCalledWith('run', 'execution', { resourceProject: 'proj-42' })
  })

  it('is aria-disabled when user lacks execution:run permission', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })

    renderButton()

    const button = screen.getByRole('button', { name: 'Retry run' })
    expect(button).toHaveAttribute('aria-disabled', 'true')
  })

  it('is aria-disabled while permission check is in flight', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: true, isError: false })

    renderButton()

    const button = screen.getByRole('button', { name: 'Retry run' })
    expect(button).toHaveAttribute('aria-disabled', 'true')
  })

  it('does not open dialog when button is disabled', async () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })
    const user = userEvent.setup()
    renderButton()

    await user.click(screen.getByRole('button', { name: 'Retry run' }))

    expect(screen.queryByText('Retry run?')).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = renderButton()
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
